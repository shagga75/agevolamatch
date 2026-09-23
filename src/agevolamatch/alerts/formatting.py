from __future__ import annotations

from agevolamatch.matching.models import MatchResult


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
    lines.append("\nEsta alerta es orientativa: verificá siempre los requisitos en la fuente oficial.")

    return subject, "\n".join(lines)
