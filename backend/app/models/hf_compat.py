"""
Shared helpers for HuggingFace model loaders.

`transformers` ≥ 4.43 renamed the `use_auth_token` keyword to `token` in the
`from_pretrained` family of functions, and a number of model classes (e.g.
`DepthAnythingForDepthEstimation`, `GroundingDino`) do not forward `**kwargs`
into their `__init__`, so passing `use_auth_token=...` raises
`TypeError: __init__() got an unexpected keyword argument 'use_auth_token'`.

This module exposes a single `_auth_kwargs()` helper that returns only the kwarg
the current installed `transformers` version understands, so the three loader
modules can stay agnostic of which version is installed.
"""
from __future__ import annotations

import logging
from typing import Any, Mapping

_log = logging.getLogger("aicss.models")

# Resolved at import time once — re-checked on each call to keep things robust
# against mock/patch scenarios in tests.
_auth_kwarg_name: str | None = None


def _resolve_auth_kwarg() -> str:
    """Return ``"token"`` or ``"use_auth_token"`` depending on transformers version.

    Probes ``transformers.PreTrainedModel.from_pretrained`` (cheap: the function
    object already exists at import time) and inspects its signature. Falls back
    to ``"token"`` when the kwarg is missing from both names, which means
    authentication is not supported by this transformers version.
    """
    global _auth_kwarg_name
    if _auth_kwarg_name is not None:
        return _auth_kwarg_name

    try:
        import inspect
        from transformers import PreTrainedModel

        sig = inspect.signature(PreTrainedModel.from_pretrained)
        params = sig.parameters

        if "token" in params:
            _auth_kwarg_name = "token"
        elif "use_auth_token" in params:
            _auth_kwarg_name = "use_auth_token"
        else:
            _auth_kwarg_name = ""
            _log.warning(
                "[hf_compat] transformers.from_pretrained accepts neither "
                "'token' nor 'use_auth_token' — HF authentication will be skipped."
            )
    except Exception as e:  # pragma: no cover — defensive only
        _auth_kwarg_name = "token"
        _log.debug("[hf_compat] Could not introspect transformers signature: %s", e)

    return _auth_kwarg_name


def auth_kwargs(hf_token: str | None) -> dict[str, Any]:
    """Return a dict with the auth kwarg supported by the installed transformers.

    Pass ``hf_token=settings.hf_token`` (which may be empty string) and the helper
    decides whether to inject the kwarg at all. An empty / falsy token means
    "no authentication", so we omit the kwarg to keep behaviour identical to the
    pre-token era.
    """
    if not hf_token:
        return {}

    name = _resolve_auth_kwarg()
    if not name:
        return {}
    return {name: hf_token}
