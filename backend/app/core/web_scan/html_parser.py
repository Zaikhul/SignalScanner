from __future__ import annotations

from html.parser import HTMLParser
from typing import Dict, List, Optional, Set
from urllib.parse import urljoin, urlsplit


class FormField:
    def __init__(self, name: str, input_type: str):
        self.name = name
        self.input_type = input_type

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "type": self.input_type,
            "secret_value_discarded": self.input_type.lower() == "password",
        }


DiscoveredField = FormField


class DiscoveredForm:
    def __init__(self, action: str, method: str, fields: List[FormField]):
        self.action = action
        self.method = method.upper() if method else "GET"
        self.fields = fields

    @property
    def has_password_field(self) -> bool:
        return any(f.input_type.lower() == "password" for f in self.fields)

    @property
    def has_csrf_token(self) -> bool:
        return any(
            any(k in f.name.lower() for k in ("csrf", "token", "xsrf", "_token"))
            for f in self.fields
        )


class WebPageHtmlParser(HTMLParser):
    """Safe streaming HTML parser using standard library html.parser."""

    def __init__(self, base_url: str):
        super().__init__(convert_charrefs=True)
        self.base_url = base_url
        self.base_parts = urlsplit(base_url)
        self.base_domain = self.base_parts.hostname or ""

        self.forms: List[DiscoveredForm] = []
        self._current_form_action: Optional[str] = None
        self._current_form_method: str = "GET"
        self._current_form_fields: List[FormField] = []
        self._inside_form: bool = False

        self.discovered_links: List[str] = []
        self._seen_links: Set[str] = set()

    def handle_starttag(self, tag: str, attrs: List[tuple[str, Optional[str]]]) -> None:
        tag = tag.lower()
        attr_dict = {k.lower(): (v or "") for k, v in attrs}

        # 1. Parse Links <a>
        if tag == "a" and "href" in attr_dict:
            href = attr_dict["href"].strip()
            if href and not href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
                abs_url = urljoin(self.base_url, href)
                parts = urlsplit(abs_url)
                # Enforce same-host or subdomain ownership and max 10 links
                if parts.hostname and (
                    parts.hostname == self.base_domain
                    or parts.hostname.endswith("." + self.base_domain)
                ):
                    clean_url = abs_url.split("#")[0]
                    if clean_url not in self._seen_links and len(self.discovered_links) < 10:
                        self._seen_links.add(clean_url)
                        self.discovered_links.append(clean_url)

        # 2. Parse Form Open <form>
        elif tag == "form":
            self._inside_form = True
            action_raw = attr_dict.get("action", "")
            self._current_form_action = urljoin(self.base_url, action_raw) if action_raw else self.base_url
            self._current_form_method = attr_dict.get("method", "GET").upper()
            self._current_form_fields = []

        # 3. Parse Form Inputs
        elif self._inside_form and tag in ("input", "textarea", "select"):
            name = attr_dict.get("name", "").strip()
            input_type = attr_dict.get("type", "text").lower() if tag == "input" else tag
            if name:
                self._current_form_fields.append(FormField(name=name, input_type=input_type))

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "form" and self._inside_form:
            self._inside_form = False
            action_url = self._current_form_action or self.base_url
            parts = urlsplit(action_url)
            # Only retain form if action belongs to same host or subdomain
            if not parts.hostname or (
                parts.hostname == self.base_domain
                or parts.hostname.endswith("." + self.base_domain)
            ):
                self.forms.append(
                    DiscoveredForm(
                        action=action_url,
                        method=self._current_form_method,
                        fields=self._current_form_fields,
                    )
                )
            self._current_form_action = None
            self._current_form_fields = []


def parse_page_html(base_url: str, html_text: str) -> tuple[List[DiscoveredForm], List[str]]:
    """Convenience helper to extract forms and links from an HTML document."""
    parser = WebPageHtmlParser(base_url=base_url)
    try:
        parser.feed(html_text)
    except Exception:
        pass
    return parser.forms, parser.discovered_links
