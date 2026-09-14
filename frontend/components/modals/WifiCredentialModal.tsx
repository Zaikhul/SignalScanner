"use client";

import React, { useEffect, useState, useRef } from "react";
import {
  X,
  Lock,
  Eye,
  EyeSlash,
  Warning,
  ShieldCheck,
  PlugsConnected,
} from "@phosphor-icons/react";
import { useScannerStore } from "@/lib/store";
import { apiClient } from "@/lib/apiClient";

export function WifiCredentialModal() {
  const {
    activeSession,
    credentialModalOpen,
    setCredentialModalOpen,
    targetToAssociate,
    setActiveAssociation,
    updateAssociationState,
  } = useScannerStore();

  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [capsLockActive, setCapsLockActive] = useState(false);
  const [authorizedUseConfirmed, setAuthorizedUseConfirmed] = useState(false);
  const [saveProfile, setSaveProfile] = useState(false);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const passwordInputRef = useRef<HTMLInputElement>(null);

  // Security type inspection
  const rawSecurity = targetToAssociate?.extra?.security || targetToAssociate?.extra?.auth || "WPA2";
  const isOpenNetwork =
    rawSecurity.toLowerCase().includes("open") ||
    rawSecurity.toLowerCase().includes("none");

  useEffect(() => {
    if (credentialModalOpen) {
      setPassword("");
      setShowPassword(false);
      setAuthorizedUseConfirmed(false);
      setSaveProfile(false);
      setErrorMessage(null);
      setTimeout(() => {
        if (!isOpenNetwork && passwordInputRef.current) {
          passwordInputRef.current.focus();
        }
      }, 100);
    }
  }, [credentialModalOpen, isOpenNetwork]);

  if (!credentialModalOpen || !targetToAssociate || !activeSession) {
    return null;
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.getModifierState && e.getModifierState("CapsLock")) {
      setCapsLockActive(true);
    } else {
      setCapsLockActive(false);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!authorizedUseConfirmed) return;
    if (!isOpenNetwork && !password.trim()) return;

    setIsSubmitting(true);
    setErrorMessage(null);

    const ssidName = targetToAssociate.display_name || "Unknown SSID";
    const secHint = isOpenNetwork
      ? "open"
      : rawSecurity.toLowerCase().includes("wpa3")
      ? "wpa3_sae"
      : "wpa2_personal";

    try {
      // 1. Create association draft in backend
      const draft = await apiClient.createAssociation(activeSession.id, {
        target_id: targetToAssociate.target_id,
        security_hint: secHint,
        ssid: ssidName,
        bssid_hash: targetToAssociate.target_id,
      });
      setActiveAssociation(draft);

      // 2. Direct ephemeral credential submission to local collector agent (port 8001)
      if (!isOpenNetwork) {
        await apiClient.sendDirectAssociate({
          association_id: draft.id,
          target_id: targetToAssociate.target_id,
          ssid: ssidName,
          security_type: secHint,
          password: password,
          save_profile: saveProfile,
          timeout_seconds: 30,
        });
      }

      // 3. Trigger connection in backend (Zero-Secret guarantee: No password parameter!)
      await apiClient.connectAssociation(draft.id, {
        target_id: targetToAssociate.target_id,
        security_hint: secHint,
        authorized_use_confirmed: true,
        save_profile: saveProfile,
        timeout_seconds: 30,
      });

      updateAssociationState("associating");
      setCredentialModalOpen(false);
    } catch (err: any) {
      console.error("Connection attempt failed", err);
      setErrorMessage(err.message || "Gagal mengirim perintah koneksi.");
    } finally {
      // Explicit zeroization of credential state in memory
      setPassword("");
      setIsSubmitting(false);
    }
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="modal-wifi-connect-title"
      className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/70 backdrop-blur-sm animate-fade-in"
    >
      <div className="w-full max-w-md bg-zinc-900 border border-white/10 rounded-[var(--radius-panel)] p-6 shadow-2xl space-y-4">
        {/* Modal Header */}
        <div className="flex items-center justify-between border-b border-white/10 pb-3">
          <div className="flex items-center gap-2">
            <div className="p-2 rounded-lg bg-[var(--color-surface)] border border-white/10 text-[var(--color-signal)]">
              <PlugsConnected size={18} weight="bold" />
            </div>
            <div>
              <h2 id="modal-wifi-connect-title" className="text-sm font-semibold text-zinc-100">
                Hubungkan ke WiFi
              </h2>
              <p className="text-xs text-zinc-400 truncate max-w-[240px]">
                {targetToAssociate.display_name || "Access Point"}
              </p>
            </div>
          </div>
          <button
            type="button"
            onClick={() => setCredentialModalOpen(false)}
            className="p-1.5 rounded-[var(--radius-control)] text-zinc-400 hover:text-zinc-100 hover:bg-white/5 transition"
            aria-label="Tutup modal"
          >
            <X size={16} />
          </button>
        </div>

        {/* Disclaimer Banner (PRD Section 13.4) */}
        <div className="p-3 rounded-[var(--radius-control)] bg-zinc-950 border border-white/10 text-zinc-400 text-xs leading-relaxed flex gap-2.5">
          <ShieldCheck size={18} className="shrink-0 text-[var(--color-signal)] mt-0.5" />
          <p>
            Fitur ini hanya untuk jaringan yang Anda kelola atau izinkan. Inventaris host bukan peta lokasi dan bukan uji keamanan.
          </p>
        </div>

        {errorMessage && (
          <div className="p-3 rounded bg-red-950/40 border border-red-500/30 text-red-300 text-xs flex items-center gap-2">
            <Warning size={16} className="shrink-0 text-red-400" />
            <span>{errorMessage}</span>
          </div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          {/* Password Field (Only for non-Open networks) */}
          {!isOpenNetwork ? (
            <div className="space-y-1.5">
              <label
                htmlFor="wifi-password-input"
                className="text-xs font-medium text-zinc-300 flex items-center justify-between"
              >
                <span>Kata Sandi Jaringan ({rawSecurity})</span>
                {capsLockActive && (
                  <span className="text-[10px] text-amber-400 flex items-center gap-1 font-normal">
                    <Warning size={12} /> Caps Lock aktif
                  </span>
                )}
              </label>

              <div className="relative">
                <input
                  ref={passwordInputRef}
                  id="wifi-password-input"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  onKeyDown={handleKeyDown}
                  placeholder="Masukkan kata sandi..."
                  className="w-full bg-zinc-950 border border-white/10 rounded-[var(--radius-control)] px-3 py-2 pr-10 text-xs text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-[var(--color-signal)] transition font-mono"
                />
                <button
                  type="button"
                  onClick={() => setShowPassword(!showPassword)}
                  className="absolute right-2.5 top-1/2 -translate-y-1/2 text-zinc-400 hover:text-zinc-200 transition p-1"
                  aria-label={showPassword ? "Sembunyikan kata sandi" : "Tampilkan kata sandi"}
                >
                  {showPassword ? <EyeSlash size={15} /> : <Eye size={15} />}
                </button>
              </div>
            </div>
          ) : (
            <div className="p-3 rounded bg-zinc-950 border border-white/10 text-xs text-zinc-400">
              Jaringan ini bersifat <strong>Open</strong> dan tidak memerlukan kata sandi.
            </div>
          )}

          {/* Profile Saving Option (Default: Jangan simpan) */}
          <div className="space-y-2 pt-1 border-t border-white/10">
            <span className="text-[11px] font-medium text-zinc-400 block">
              Penyimpanan Profil Jaringan
            </span>
            <div className="flex items-center gap-4 text-xs">
              <label className="flex items-center gap-2 cursor-pointer text-zinc-300">
                <input
                  type="radio"
                  name="save_profile_opt"
                  checked={!saveProfile}
                  onChange={() => setSaveProfile(false)}
                  className="accent-[var(--color-signal)]"
                />
                <span>Jangan simpan profil (Default)</span>
              </label>

              <label className="flex items-center gap-2 cursor-pointer text-zinc-400">
                <input
                  type="radio"
                  name="save_profile_opt"
                  checked={saveProfile}
                  onChange={() => setSaveProfile(true)}
                  className="accent-[var(--color-signal)]"
                />
                <span>Simpan di sistem</span>
              </label>
            </div>
          </div>

          {/* Authorized Use Gate Checkbox (FR-CON-06) */}
          <div className="pt-2 border-t border-white/10">
            <label className="flex items-start gap-2.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={authorizedUseConfirmed}
                onChange={(e) => setAuthorizedUseConfirmed(e.target.checked)}
                className="mt-0.5 rounded border-white/20 bg-zinc-950 text-[var(--color-signal)] focus:ring-0 accent-[var(--color-signal)]"
              />
              <span className="text-xs text-zinc-200 font-medium leading-tight">
                Saya berwenang pada jaringan ini
              </span>
            </label>
          </div>

          {/* Modal Action Buttons */}
          <div className="flex items-center justify-end gap-2 pt-3 border-t border-white/10">
            <button
              type="button"
              onClick={() => setCredentialModalOpen(false)}
              className="py-2 px-4 rounded-[var(--radius-control)] border border-white/10 hover:bg-white/5 text-xs text-zinc-300 transition"
            >
              Batal
            </button>
            <button
              type="submit"
              disabled={!authorizedUseConfirmed || (!isOpenNetwork && !password.trim()) || isSubmitting}
              className="py-2 px-5 rounded-[var(--radius-control)] bg-[var(--color-signal)] hover:bg-[var(--color-signal)]/90 text-zinc-950 text-xs font-semibold flex items-center gap-1.5 transition disabled:opacity-40 disabled:cursor-not-allowed"
            >
              <PlugsConnected size={15} weight="bold" />
              {isSubmitting ? "Menghubungkan..." : "Hubungkan"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
