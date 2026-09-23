from __future__ import annotations

from agevolamatch.matching.models import MatchResult
from agevolamatch.tenders.models import TenderMatchResult

_FOOTER = "\nEsta alerta es orientativa: verificá siempre los requisitos en la fuente oficial."


def format_alert_message(subscription_name: str, result: MatchResult) -> tuple[str, str]:
    incentive = result.incentive
    subject = f"[AgevolaMatch/{subscription_name}] {incentive.title} (score {result.score})"

    lines = [
        incentive.title,
        f"Score: {result.score}/100",
        f"Estado: {incentive.status}",
    ]
    if incentive.close_date:
        lines.append(f"Cierra: {incentive.close_date.date().isoformat()}")
    if incentive.url:
        lines.append(f"URL: {incentive.url}")
    if result.explanation.reasons_for:
        lines.append("\nA favor:")
        lines.extend(f"  + {r}" for r in result.explanation.reasons_for)
    if result.explanation.reasons_against:
        lines.append("\nEn contra:")
        lines.extend(f"  - {r}" for r in result.explanation.reasons_against)
    if result.explanation.unverifiable:
        lines.append("\nA verificar:")
        lines.extend(f"  ? {r}" for r in result.explanation.unverifiable)
    lines.append(_FOOTER)

    return subject, "\n".join(lines)


def format_tender_alert_message(subscription_name: str, result: TenderMatchResult) -> tuple[str, str]:
    tender = result.tender
    subject = f"[AgevolaMatch/{subscription_name}] {tender.title} (score {result.score})"

    lines = [
        tender.title,
        f"Score: {result.score}/100",
        f"Fuente: {tender.source}",
        f"Estado: {tender.status}",
    ]
    if tender.close_date:
        lines.append(f"Cierra: {tender.close_date.date().isoformat()}")
    if tender.estimated_value is not None:
        lines.append(f"Importe estimado: {tender.estimated_value:.0f} {tender.estimated_value_currency or ''}".strip())
    if tender.url:
        lines.append(f"URL: {tender.url}")
    if result.explanation.reasons_for:
        lines.append("\nA favor:")
        lines.extend(f"  + {r}" for r in result.explanation.reasons_for)
    if result.explanation.reasons_against:
        lines.append("\nEn contra:")
        lines.extend(f"  - {r}" for r in result.explanation.reasons_against)
    if result.explanation.unverifiable:
        lines.append("\nA verificar:")
        lines.extend(f"  ? {r}" for r in result.explanation.unverifiable)
    lines.append(_FOOTER)

    return subject, "\n".join(lines)
