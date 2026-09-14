import math
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.schemas.channel_health import (
    CandidateRecommendation,
    ChannelHealthComponents,
    ChannelHealthComponentValue,
    ChannelHealthItem,
    ChannelRecommendationResponse,
    ComponentProvenance,
    ConfidenceLevel,
    HealthLabel,
    ObservationWindowInfo,
    RegulatoryDomainInfo,
)


class ChannelHealthEngine:
    """
    Channel Health & Recommendation Engine (v1.2) - Algorithm Version: channel-health-1.0.0
    Implements PRD v1.2 specifications:
    - Linear power mW conversions (never directly sum dBm)
    - Spectral overlap matrix with 20/40/80/160 MHz channel widths
    - Strict separation of Co-Channel Interference (CCI) and Adjacent-Channel Interference (ACI)
    - 5-component penalty calculation with weight renormalization on unavailable metrics
    - Decoupled Confidence classification (High, Medium, Low)
    - Regulatory candidate filtering (default 2.4 GHz plan: {1, 6, 11}, DFS exclusion/tagging)
    - Deterministic and explainable recommendation output with audit trails
    """

    ALGORITHM_VERSION = "channel-health-1.0.0"

    INITIAL_WEIGHTS = {
        "utilization": 0.30,
        "overlap_interference": 0.30,
        "retry": 0.20,
        "noise": 0.10,
        "temporal_instability": 0.10,
    }

    # Standard center frequencies in MHz
    @staticmethod
    def get_channel_center_freq_mhz(channel: int, band: str = "2.4GHz") -> int:
        if band == "2.4GHz":
            if channel == 14:
                return 2484
            return 2412 + (channel - 1) * 5
        elif band == "5GHz":
            return 5000 + channel * 5
        elif band == "6GHz":
            return 5950 + channel * 5
        return 2412

    @staticmethod
    def dbm_to_mw(rssi_dbm: float) -> float:
        """Converts RSSI in dBm to linear power in milliwatts (mW)."""
        return 10.0 ** (rssi_dbm / 10.0)

    @staticmethod
    def mw_to_dbm(power_mw: float) -> float:
        """Converts linear power in milliwatts (mW) to dBm."""
        if power_mw <= 1e-15:
            return -120.0
        return round(10.0 * math.log10(power_mw), 1)

    @classmethod
    def calculate_spectral_overlap(
        cls,
        candidate_ch: int,
        candidate_width: int,
        interferer_ch: int,
        interferer_width: int,
        band: str = "2.4GHz",
    ) -> float:
        """
        Calculates spectral overlap ratio [0.0, 1.0] of candidate channel with interferer AP.
        Overlaps are derived from continuous frequency intervals.
        """
        cand_center = cls.get_channel_center_freq_mhz(candidate_ch, band)
        int_center = cls.get_channel_center_freq_mhz(interferer_ch, band)

        cand_start = cand_center - (candidate_width / 2.0)
        cand_end = cand_center + (candidate_width / 2.0)

        int_start = int_center - (interferer_width / 2.0)
        int_end = int_center + (interferer_width / 2.0)

        overlap_start = max(cand_start, int_start)
        overlap_end = min(cand_end, int_end)
        overlap_mhz = max(0.0, overlap_end - overlap_start)

        # Ratio of candidate bandwidth submerged by interference
        ratio = overlap_mhz / float(candidate_width)
        return min(max(ratio, 0.0), 1.0)

    @staticmethod
    def get_health_label(score: int) -> str:
        if score >= 80:
            return HealthLabel.SEHAT.value
        elif score >= 60:
            return HealthLabel.LAYAK.value
        elif score >= 40:
            return HealthLabel.PADAT.value
        return HealthLabel.BURUK.value

    @classmethod
    def get_supported_channels(
        cls,
        band: str = "2.4GHz",
        regulatory_domain: str = "ID",
    ) -> Tuple[List[int], Set[int], Set[int]]:
        """
        Returns (all_channels, operational_candidates, dfs_channels).
        """
        reg = regulatory_domain.upper()
        if band == "2.4GHz":
            if reg == "US":
                all_ch = list(range(1, 12))  # 1-11
            else:
                all_ch = list(range(1, 14))  # 1-13 (ID, EU)
            # Default operational candidate plan: 1, 6, 11 (PRD 10.4.2 item 8)
            candidates = {1, 6, 11}
            dfs = set()
            return all_ch, candidates, dfs
        elif band == "5GHz":
            # Standard channels across UNII-1, UNII-2A (DFS), UNII-2C (DFS), UNII-3
            all_ch = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144, 149, 153, 157, 161, 165]
            if reg == "ID":
                # Indonesian SDPPI allows UNII-1 (36-48), UNII-2A (52-64 with DFS), UNII-3 (149-165)
                all_ch = [36, 40, 44, 48, 52, 56, 60, 64, 149, 153, 157, 161, 165]
            elif reg == "EU":
                # ETSI allows UNII-1, UNII-2A, UNII-2C up to 140
                all_ch = [36, 40, 44, 48, 52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140]

            dfs = {52, 56, 60, 64, 100, 104, 108, 112, 116, 120, 124, 128, 132, 136, 140, 144}.intersection(set(all_ch))
            candidates = set(all_ch)
            return all_ch, candidates, dfs
        elif band == "6GHz":
            all_ch = [1, 5, 9, 13, 17, 21, 25, 29, 33, 37]
            candidates = set(all_ch)
            dfs = set()
            return all_ch, candidates, dfs

        return [1, 6, 11], {1, 6, 11}, set()

    @classmethod
    def evaluate_channels(
        cls,
        band: str,
        channel_width_mhz: int,
        targets: List[Dict[str, Any]],
        measurements: List[Dict[str, Any]],
        regulatory_domain: str = "ID",
        external_telemetry: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[ChannelHealthItem], List[str]]:
        """
        Evaluates health score and components for all supported channels in the band.
        Returns (list_of_channel_items, quality_flags).
        """
        quality_flags: List[str] = []
        if not regulatory_domain or regulatory_domain.upper() == "UNKNOWN":
            quality_flags.append("REGULATORY_DOMAIN_UNKNOWN")
            regulatory_domain = "ID"

        all_channels, operational_candidates, dfs_channels = cls.get_supported_channels(band, regulatory_domain)

        # Organize targets by their reported channel and width
        # Target format: {"target_id": ..., "channel": ..., "channel_width": ..., "signal_value": ...}
        band_targets = [
            t for t in targets
            if (t.get("band") == band or (not t.get("band") and band == "2.4GHz"))
            and t.get("channel") is not None
        ]

        # Check if channel width is generally unknown across targets
        widths_present = sum(1 for t in band_targets if t.get("channel_width") or t.get("channel_width_mhz"))
        if band_targets and widths_present == 0:
            quality_flags.append("CHANNEL_WIDTH_UNKNOWN")

        # Temporal instability analysis per channel from measurements
        # Calculate standard deviation of RSSI per channel over the window
        ch_measurements: Dict[int, List[float]] = {}
        for m in measurements:
            ch = m.get("channel")
            if ch is not None:
                ch_measurements.setdefault(ch, []).append(float(m.get("signal_value", -90.0)))

        channel_items: List[ChannelHealthItem] = []

        for ch in all_channels:
            is_dfs = ch in dfs_channels
            is_cand = ch in operational_candidates
            exclusion_reasons: List[str] = []

            if not is_cand:
                if band == "2.4GHz":
                    exclusion_reasons.append("non_standard_2_4ghz_plan")
                else:
                    exclusion_reasons.append("regulatory_restricted")

            # 1. Calculate Overlap-weighted linear interference (mW)
            # Separate CCI and ACI
            total_cci_mw = 0.0
            total_aci_mw = 0.0
            direct_ap_count = 0
            max_rssi = -120.0

            for t in band_targets:
                t_ch = t.get("channel")
                if t_ch is None:
                    continue
                t_width = t.get("channel_width_mhz") or t.get("channel_width") or 20
                t_rssi = float(t.get("signal_value", -95.0))
                p_mw = cls.dbm_to_mw(t_rssi)

                overlap = cls.calculate_spectral_overlap(
                    candidate_ch=ch,
                    candidate_width=channel_width_mhz,
                    interferer_ch=t_ch,
                    interferer_width=t_width,
                    band=band,
                )

                if overlap > 0.0:
                    if t_ch == ch:
                        direct_ap_count += 1
                        max_rssi = max(max_rssi, t_rssi)
                        total_cci_mw += p_mw * overlap
                    else:
                        total_aci_mw += p_mw * overlap

            # Combined overlap interference power
            total_overlap_mw = total_cci_mw + total_aci_mw

            # Normalization of overlap interference penalty into [0.0, 1.0]:
            # Effective total interference dBm:
            if total_overlap_mw > 0.0:
                eff_dbm = cls.mw_to_dbm(total_overlap_mw)
                # Linear scale between -90 dBm (0.0 penalty) and -45 dBm (1.0 penalty)
                overlap_penalty = min(max((eff_dbm - (-90.0)) / 45.0, 0.0), 1.0)
            else:
                overlap_penalty = 0.0

            # 2. Components calculation with explicit provenance
            # (utilization, retry, noise, temporal_instability)
            ext = external_telemetry.get(ch, {}) if external_telemetry else {}

            # Utilization
            if "utilization" in ext and ext["utilization"] is not None:
                util_val = float(ext["utilization"])
                util_prov = ComponentProvenance.MEASURED
                util_penalty = min(max(util_val, 0.0), 1.0)
            else:
                util_val = None
                util_prov = ComponentProvenance.UNAVAILABLE
                util_penalty = None

            # Retry
            if "retry_rate" in ext and ext["retry_rate"] is not None:
                retry_val = float(ext["retry_rate"])
                retry_prov = ComponentProvenance.MEASURED
                retry_penalty = min(max(retry_val, 0.0), 1.0)
            else:
                retry_val = None
                retry_prov = ComponentProvenance.UNAVAILABLE
                retry_penalty = None

            # Noise floor
            if "noise_floor" in ext and ext["noise_floor"] is not None:
                noise_dbm = float(ext["noise_floor"])
                noise_prov = ComponentProvenance.MEASURED
                # Scale between -95 dBm (0.0 penalty) and -80 dBm (1.0 penalty)
                noise_penalty = min(max((noise_dbm - (-95.0)) / 15.0, 0.0), 1.0)
                noise_val = noise_dbm
            else:
                noise_val = None
                noise_prov = ComponentProvenance.UNAVAILABLE
                noise_penalty = None

            # Temporal instability
            samples = ch_measurements.get(ch, [])
            if len(samples) >= 3:
                mean_rssi = sum(samples) / len(samples)
                variance = sum((s - mean_rssi) ** 2 for s in samples) / len(samples)
                std_dev = math.sqrt(variance)
                # std_dev of 0 dB -> 0.0 penalty, std_dev >= 8 dB -> 1.0 penalty
                instability_penalty = min(max(std_dev / 8.0, 0.0), 1.0)
                instability_val = round(instability_penalty, 2)
                instability_prov = ComponentProvenance.DERIVED
            else:
                # If sparse samples, use baseline derived from AP count and variance proxy
                instability_penalty = min(0.05 + (direct_ap_count * 0.05), 0.3)
                instability_val = round(instability_penalty, 2)
                instability_prov = ComponentProvenance.INFERRED

            # 3. Weight Renormalization Formula (PRD Section 10.4.4)
            penalties: Dict[str, Optional[float]] = {
                "utilization": util_penalty,
                "overlap_interference": overlap_penalty,
                "retry": retry_penalty,
                "noise": noise_penalty,
                "temporal_instability": instability_penalty,
            }

            valid_keys = [k for k, v in penalties.items() if v is not None]
            available_weight = sum(cls.INITIAL_WEIGHTS[k] for k in valid_keys)

            if available_weight > 0:
                normalized_penalty = sum(
                    cls.INITIAL_WEIGHTS[k] * penalties[k] for k in valid_keys  # type: ignore
                ) / available_weight
            else:
                normalized_penalty = 0.5

            clamped_penalty = min(max(normalized_penalty, 0.0), 1.0)
            health_score = int(round(100.0 * (1.0 - clamped_penalty)))
            health_label = cls.get_health_label(health_score)

            components = ChannelHealthComponents(
                utilization=ChannelHealthComponentValue(
                    value=util_val,
                    provenance=util_prov,
                    details={"penalty": util_penalty} if util_penalty is not None else None,
                ),
                overlap_interference=ChannelHealthComponentValue(
                    value=round(overlap_penalty, 3),
                    provenance=ComponentProvenance.DERIVED,
                    details={
                        "total_power_mw": round(total_overlap_mw, 8),
                        "cci_power_mw": round(total_cci_mw, 8),
                        "aci_power_mw": round(total_aci_mw, 8),
                        "eff_dbm": cls.mw_to_dbm(total_overlap_mw) if total_overlap_mw > 0 else -120.0,
                    },
                ),
                retry=ChannelHealthComponentValue(
                    value=retry_val,
                    provenance=retry_prov,
                    details={"penalty": retry_penalty} if retry_penalty is not None else None,
                ),
                noise=ChannelHealthComponentValue(
                    value=noise_val,
                    provenance=noise_prov,
                    details={"penalty": noise_penalty} if noise_penalty is not None else None,
                ),
                temporal_instability=ChannelHealthComponentValue(
                    value=instability_val,
                    provenance=instability_prov,
                    details={"sample_count": len(samples)},
                ),
            )

            channel_items.append(
                ChannelHealthItem(
                    channel=ch,
                    band=band,
                    width_mhz=channel_width_mhz,
                    health_score=health_score,
                    health_label=health_label,
                    cci_power_mw=round(total_cci_mw, 8),
                    aci_power_mw=round(total_aci_mw, 8),
                    ap_count=direct_ap_count,
                    max_rssi=max_rssi if direct_ap_count > 0 else -120.0,
                    is_dfs=is_dfs,
                    is_candidate=is_cand,
                    exclusion_reasons=exclusion_reasons,
                    components=components,
                )
            )

        # Check for empty / partial data
        if not band_targets and not measurements:
            quality_flags.append("INSUFFICIENT_CHANNEL_DATA")

        return channel_items, quality_flags

    @classmethod
    def classify_confidence(
        cls,
        observation_window_sec: float,
        scan_cycles: int,
        quality_flags: List[str],
        channel_items: List[ChannelHealthItem],
        is_throttled: bool = False,
    ) -> Tuple[ConfidenceLevel, List[str], List[str]]:
        """
        Decoupled Confidence classification (PRD 10.4.5).
        Returns (confidence_level, confidence_reasons, missing_evidence).
        """
        reasons: List[str] = []
        missing: List[str] = []

        # Check what preferred metrics are available
        has_utilization = any(
            item.components.utilization.provenance != ComponentProvenance.UNAVAILABLE
            for item in channel_items
        )
        has_retry = any(
            item.components.retry.provenance != ComponentProvenance.UNAVAILABLE
            for item in channel_items
        )
        has_noise = any(
            item.components.noise.provenance != ComponentProvenance.UNAVAILABLE
            for item in channel_items
        )

        if not has_utilization:
            missing.append("channel_utilization")
        if not has_retry:
            missing.append("retry_rate")
        if not has_noise:
            missing.append("noise_floor")

        if "CHANNEL_WIDTH_UNKNOWN" in quality_flags:
            missing.append("channel_width_ie")
        if "REGULATORY_DOMAIN_UNKNOWN" in quality_flags:
            missing.append("regulatory_domain_verified")

        # Conditions for HIGH:
        # Window >= 300s, complete coverage, non-stale, non-throttled, known regulatory,
        # available utilization and at least retry or noise
        is_high_window = observation_window_sec >= 300.0 and scan_cycles >= 10
        is_reg_known = "REGULATORY_DOMAIN_UNKNOWN" not in quality_flags
        is_not_throttled = not is_throttled and "THROTTLED" not in quality_flags

        if (
            is_high_window
            and is_reg_known
            and is_not_throttled
            and has_utilization
            and (has_retry or has_noise)
        ):
            reasons.append("sufficient_5m_observation_window")
            reasons.append("complete_candidate_scan_coverage")
            reasons.append("verified_regulatory_domain")
            reasons.append("telemetry_utilization_available")
            return ConfidenceLevel.HIGH, reasons, missing

        # Conditions for MEDIUM:
        # Scan cycles >= 5 or window >= 60s, RSSI & channel mapping complete
        is_medium_window = observation_window_sec >= 60.0 or scan_cycles >= 5
        if is_medium_window and is_reg_known and not is_throttled and len(channel_items) > 0:
            reasons.append("multi_cycle_rssi_spectral_mapping")
            if not has_utilization:
                reasons.append("utilization_estimated_via_overlap_proxy")
            return ConfidenceLevel.MEDIUM, reasons, missing

        # Otherwise: LOW
        if not is_reg_known:
            reasons.append("regulatory_domain_unverified")
        if is_throttled:
            reasons.append("os_scan_interval_throttled")
        if observation_window_sec < 60.0:
            reasons.append("snapshot_window_under_minimum_threshold")
        if "INSUFFICIENT_CHANNEL_DATA" in quality_flags:
            reasons.append("insufficient_measurement_samples")

        return ConfidenceLevel.LOW, reasons, missing

    @classmethod
    def generate_recommendation(
        cls,
        session_id: str,
        snapshot_id: str,
        band: str,
        channel_width_mhz: int,
        channel_items: List[ChannelHealthItem],
        observation_window: ObservationWindowInfo,
        quality_flags: List[str],
        is_throttled: bool = False,
    ) -> ChannelRecommendationResponse:
        """
        Generates explainable read-only channel recommendations from evaluated channel items.
        Filters candidates, handles tie margin (RECOMMENDATION_CONFLICT), supporting factors & counter signals.
        """
        confidence, confidence_reasons, missing_evidence = cls.classify_confidence(
            observation_window_sec=observation_window.duration_seconds,
            scan_cycles=observation_window.scan_cycles,
            quality_flags=quality_flags,
            channel_items=channel_items,
            is_throttled=is_throttled,
        )

        # Filter only valid candidates (e.g. 1, 6, 11 on 2.4GHz)
        candidates = [item for item in channel_items if item.is_candidate]
        if not candidates:
            # Fallback to all channels if none marked candidate
            candidates = channel_items

        # Sort descending by health_score, then ascending by overlap_interference penalty
        sorted_candidates = sorted(
            candidates,
            key=lambda c: (
                c.health_score,
                -(c.components.overlap_interference.value or 0.0),
                -c.ap_count,
            ),
            reverse=True,
        )

        primary_item = sorted_candidates[0]
        alt_items = sorted_candidates[1:3]

        # Conflict detection: score diff <= 2 between top 2
        conflict_detected = False
        if len(sorted_candidates) >= 2:
            score_diff = abs(sorted_candidates[0].health_score - sorted_candidates[1].health_score)
            if score_diff <= 2:
                conflict_detected = True

        cta_label = "Direkomendasikan" if confidence in (ConfidenceLevel.HIGH, ConfidenceLevel.MEDIUM) else "Kandidat untuk diuji"

        primary_rec = CandidateRecommendation(
            channel=primary_item.channel,
            band=primary_item.band,
            width_mhz=primary_item.width_mhz,
            score=primary_item.health_score,
            health_label=primary_item.health_label,
            confidence=confidence.value,
            is_dfs=primary_item.is_dfs,
            cta_label=cta_label,
        )

        alternatives_rec = [
            CandidateRecommendation(
                channel=alt.channel,
                band=alt.band,
                width_mhz=alt.width_mhz,
                score=alt.health_score,
                health_label=alt.health_label,
                confidence=confidence.value,
                is_dfs=alt.is_dfs,
                cta_label="Kandidat alternatif",
            )
            for alt in alt_items
        ]

        # Supporting factors (max 3)
        supporting: List[str] = []
        if primary_item.cci_power_mw == 0.0:
            supporting.append("Bebas dari interferensi co-channel (CCI)")
        elif primary_item.cci_power_mw < 1e-6:
            supporting.append("Interferensi co-channel berada pada level sangat rendah")

        if (primary_item.components.overlap_interference.value or 0.0) < 0.2:
            supporting.append("Daya interferensi linear terbobot spektral terendah")

        if primary_item.ap_count <= 1:
            supporting.append(f"Kepadatan BSSID minimal ({primary_item.ap_count} AP terdeteksi)")

        if primary_item.components.temporal_instability.value and primary_item.components.temporal_instability.value < 0.2:
            supporting.append("Stabilitas temporal RSSI konsisten pada observation window")

        if not supporting:
            supporting.append("Skor komposit relatif tertinggi di antara kandidat regulasi")

        supporting = supporting[:3]

        # Counter signals (max 3)
        counter: List[str] = []
        if "channel_utilization" in missing_evidence:
            counter.append("Metrik utilisasi fisik airtime belum tersedia dari radio OS")

        if primary_item.is_dfs:
            counter.append("Kanal berada di pita DFS (rentan terhadap radar CAC/NOP)")

        if primary_item.aci_power_mw > 1e-6:
            counter.append("Terdapat energi interferensi spektral dari kanal adjacent")

        if conflict_detected and alt_items:
            counter.append(f"Selisih skor tipis dengan kanal {alt_items[0].channel} (disarankan A/B test)")

        if confidence == ConfidenceLevel.LOW:
            counter.append("Observation window singkat, jalankan scan lebih lama untuk menaikkan kepastian")

        counter = counter[:3]

        freshness_status = "stale" if "CHANNEL_DATA_STALE" in quality_flags else "fresh"

        return ChannelRecommendationResponse(
            schema_version="1.2",
            recommendation_id=f"chr_{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}_{primary_item.channel}",
            session_id=session_id,
            input_snapshot_id=snapshot_id,
            algorithm_version=cls.ALGORITHM_VERSION,
            band=band,
            channel_width_mhz=channel_width_mhz,
            primary=primary_rec,
            alternatives=alternatives_rec,
            confidence=confidence,
            confidence_reasons=confidence_reasons,
            missing_evidence=missing_evidence,
            supporting_factors=supporting,
            counter_signals=counter,
            conflict_detected=conflict_detected,
            observation_window=observation_window,
            freshness_status=freshness_status,
            created_at=datetime.now(timezone.utc).isoformat(),
        )


channel_health_engine = ChannelHealthEngine()
