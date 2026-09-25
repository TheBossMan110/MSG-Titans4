"""
The support mailbox's reply, in the website's own look.

Email clients are not browsers: Gmail strips <style> blocks in some views
and Outlook renders with Word, so the layout is tables and every style is
inline. The fonts are the site's (Fraunces for headings, Instrument Sans for
text) with safe fallbacks for clients that load no web fonts: Georgia and
Arial look close enough that the email still reads as the same brand.

Colours are the site's tokens: cream ground, espresso ink, forest green for
the rules, blue for the AI. There is no purple.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field

CREAM = "#f5f0e8"
IVORY = "#fbf8f2"
ESPRESSO = "#2a1f17"
ESPRESSO_2 = "#3d2e22"
TAUPE = "#5a4a39"
LINE = "#e9e0d1"
RULE = "#1e3a2f"
RULE_SOFT = "#e2eee6"
AI = "#1b5e8c"
SERIF = "'Fraunces', Georgia, 'Times New Roman', serif"
SANS = "'Instrument Sans', 'Helvetica Neue', Arial, sans-serif"
MONO = "'JetBrains Mono', Consolas, 'Courier New', monospace"


@dataclass
class EmailContent:
    """What a reply says; the template decides how it looks."""

    greeting: str
    paragraphs: list[str]
    reference: str | None = None
    facts: list[tuple[str, str]] = field(default_factory=list)   # (label, value) under the reference
    steps: list[str] = field(default_factory=list)                # "what happens next"
    cta_label: str | None = None
    cta_url: str | None = None
    preheader: str = ""
    closing: str = "RaftarXpress Customer Care"


def _p(text: str) -> str:
    return (
        f'<p style="margin:0 0 14px;font-family:{SANS};font-size:15px;line-height:1.65;color:{ESPRESSO_2};">'
        f"{html.escape(text)}</p>"
    )


def render_html(content: EmailContent, *, support_hours: str | None = None, org_name: str = "RaftarXpress Logistics") -> str:
    ref_block = ""
    if content.reference:
        facts = "".join(
            f'<tr><td style="padding:6px 0;font-family:{SANS};font-size:13px;color:{TAUPE};width:40%;">{html.escape(label)}</td>'
            f'<td style="padding:6px 0;font-family:{SANS};font-size:14px;color:{ESPRESSO};font-weight:600;">{html.escape(value)}</td></tr>'
            for label, value in content.facts
        )
        ref_block = f"""
        <tr><td style="padding:4px 36px 22px;">
          <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};border:1px solid {LINE};border-radius:14px;">
            <tr><td style="padding:18px 20px;">
              <p style="margin:0 0 4px;font-family:{SANS};font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:{TAUPE};font-weight:700;">Your reference</p>
              <p style="margin:0 0 10px;font-family:{MONO};font-size:22px;color:{ESPRESSO};font-weight:600;letter-spacing:.5px;">{html.escape(content.reference)}</p>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0">{facts}</table>
            </td></tr>
          </table>
        </td></tr>"""

    steps_block = ""
    if content.steps:
        items = "".join(
            f'<tr><td valign="top" style="padding:0 12px 10px 0;width:26px;">'
            f'<div style="width:24px;height:24px;border-radius:12px;background:{ESPRESSO};color:{IVORY};font-family:{SANS};font-size:12px;font-weight:700;line-height:24px;text-align:center;">{i}</div></td>'
            f'<td style="padding:2px 0 10px;font-family:{SANS};font-size:14.5px;line-height:1.55;color:{ESPRESSO_2};">{html.escape(step)}</td></tr>'
            for i, step in enumerate(content.steps, start=1)
        )
        steps_block = f"""
        <tr><td style="padding:0 36px 10px;">
          <p style="margin:0 0 12px;font-family:{SERIF};font-size:19px;color:{ESPRESSO};">What happens next</p>
          <table role="presentation" cellpadding="0" cellspacing="0">{items}</table>
        </td></tr>"""

    cta_block = ""
    if content.cta_url and content.cta_label:
        url = html.escape(content.cta_url, quote=True)
        cta_block = f"""
        <tr><td style="padding:8px 36px 28px;">
          <table role="presentation" cellpadding="0" cellspacing="0"><tr>
            <td style="border-radius:999px;background:{ESPRESSO};">
              <a href="{url}" style="display:inline-block;padding:14px 26px;font-family:{SANS};font-size:15px;font-weight:600;color:{IVORY};text-decoration:none;border-radius:999px;">{html.escape(content.cta_label)} &rarr;</a>
            </td>
          </tr></table>
          <p style="margin:12px 0 0;font-family:{SANS};font-size:12.5px;color:{TAUPE};">Or open this link: <a href="{url}" style="color:{AI};">{url}</a></p>
        </td></tr>"""

    hours = f" · Support hours {html.escape(support_hours)}" if support_hours else ""
    paragraphs = "".join(_p(t) for t in content.paragraphs)
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light only"><title>SupportNova</title>
<link href="https://fonts.googleapis.com/css2?family=Fraunces:ital,wght@0,400;0,600;1,400&family=Instrument+Sans:wght@400;600&display=swap" rel="stylesheet">
</head>
<body style="margin:0;padding:0;background:{CREAM};">
<span style="display:none;max-height:0;overflow:hidden;opacity:0;">{html.escape(content.preheader)}</span>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{CREAM};">
  <tr><td align="center" style="padding:28px 12px;">
    <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:{IVORY};border:1px solid {LINE};border-radius:20px;overflow:hidden;">
      <tr><td style="background:{ESPRESSO};padding:24px 36px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr>
          <td style="font-family:{SERIF};font-size:24px;color:{IVORY};">Support<i>Nova</i></td>
          <td align="right" style="font-family:{SANS};font-size:11px;letter-spacing:1.6px;text-transform:uppercase;color:#d4c4aa;">{html.escape(org_name)}</td>
        </tr></table>
      </td></tr>
      <tr><td style="padding:32px 36px 8px;">
        <p style="margin:0 0 18px;font-family:{SERIF};font-size:26px;line-height:1.25;color:{ESPRESSO};">{html.escape(content.greeting)}</p>
        {paragraphs}
      </td></tr>
      {ref_block}
      {steps_block}
      {cta_block}
      <tr><td style="padding:0 36px 28px;">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{RULE_SOFT};border-radius:12px;">
          <tr><td style="padding:14px 16px;font-family:{SANS};font-size:13px;line-height:1.55;color:{RULE};">
            <b>How we handle complaints:</b> an AI reads yours and suggests what should happen; the company&rsquo;s own written rules then check every part of it, and a person reviews anything they disagree on.
          </td></tr>
        </table>
        <p style="margin:22px 0 0;font-family:{SANS};font-size:15px;color:{ESPRESSO_2};">Kind regards,<br><b>{html.escape(content.closing)}</b></p>
      </td></tr>
      <tr><td style="border-top:1px solid {LINE};padding:18px 36px;font-family:{SANS};font-size:12px;line-height:1.6;color:{TAUPE};">
        This reply was sent automatically by SupportNova{hours}. Reply to this email to add details or photos &mdash; keep the reference in the subject line.<br>
        We will never ask for your password or card number.
      </td></tr>
    </table>
  </td></tr>
</table>
</body></html>"""


def render_text(content: EmailContent, *, support_hours: str | None = None) -> str:
    """The plain-text part, for clients that show no HTML."""
    lines = [content.greeting, ""]
    for paragraph in content.paragraphs:
        lines += [paragraph, ""]
    if content.reference:
        lines += [f"Your reference: {content.reference}"]
        lines += [f"  {label}: {value}" for label, value in content.facts]
        lines.append("")
    if content.steps:
        lines.append("What happens next:")
        lines += [f"  {i}. {step}" for i, step in enumerate(content.steps, start=1)]
        lines.append("")
    if content.cta_url:
        lines += [f"{content.cta_label}: {content.cta_url}", ""]
    lines += ["Kind regards,", content.closing, "", "—", "This reply was sent automatically by SupportNova"
              + (f" · Support hours {support_hours}" if support_hours else "") + ".",
              "Reply to this email to add details; keep the reference in the subject line."]
    return "\n".join(lines)
