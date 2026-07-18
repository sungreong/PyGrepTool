BACKEND_MODE = "smart"
backend = "smart"
FEATURE_FLAG = "ALPHA_GATE"

from beta_service import beta_marker


def build_alpha_report() -> str:
    # TODO_AGENT_ALPHA: verify report payload shape.
    return f"alpha report ready: {beta_marker()}"
