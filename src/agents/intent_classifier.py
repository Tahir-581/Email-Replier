import asyncio
import json
import logging

from src.llm.client import gamma_chat_with_health_check, run_coroutine_sync
from src.llm.errors import LLMError
from src.llm.prompts import intent_classifier as prompt
from src.pipeline.state import EmailState
from src.utils.config import INTENT_BUCKETS, settings
from src.utils.json_parser import parse_llm_json
from src.utils.relocation_intent import strip_false_not_interested_for_positive_relocation

logger = logging.getLogger(__name__)


async def _pair_check_raw_responses(
    pairs: list[tuple[int, int | None]],
    subject: str,
    email_body: str,
    detected_concerns: list[str],
    history_summary: str | None,
    email_summary: str | None,
) -> list[str]:
    sem = asyncio.Semaphore(max(1, settings.INTENT_PAIR_CHECK_CONCURRENCY))

    async def fetch_one(a_id: int, b_id: int | None) -> str:
        a_label = INTENT_BUCKETS.get(a_id, "Unknown")
        b_label = INTENT_BUCKETS.get(b_id, "Unknown") if b_id else None
        user_msg = prompt.build_pair_check_prompt(
            email_body=email_body,
            detected_concerns=detected_concerns,
            intent_a_id=a_id,
            intent_a_label=a_label,
            intent_b_id=b_id,
            intent_b_label=b_label,
            subject=subject,
            history_summary=history_summary,
            email_summary=email_summary,
        )
        messages = [
            {"role": "system", "content": prompt.PAIR_CHECK_SYSTEM},
            {"role": "user", "content": user_msg},
        ]
        async with sem:
            return await gamma_chat_with_health_check(
                messages=messages,
                max_tokens=2000,
                temperature=0.0,
            )

    return await asyncio.gather(*[fetch_one(a_id, b_id) for a_id, b_id in pairs])


def intent_classifier(state: EmailState) -> EmailState:
    """
    Agent 3, Intent Classifier.
    Detects 0..N intents across the configured intent buckets plus profile type.
    """
    logger.info("[IntentClassifier] email_id=%s", state["email_id"])

    try:
        subject = state.get("subject", "") or ""
        email_body = state.get("body", "") or ""
        history_summary = state.get("history_summary")
        email_summary = (state.get("email_summary") or "").strip() or None
        detected_concerns = state.get("detected_concerns") or []
        if not isinstance(detected_concerns, list):
            detected_concerns = []
        detected_concerns = [str(x).strip() for x in detected_concerns if str(x).strip()]

        intent_ids = sorted(int(x) for x in INTENT_BUCKETS.keys() if isinstance(x, int))
        pairs: list[tuple[int, int | None]] = []
        i = 0
        while i < len(intent_ids):
            a = intent_ids[i]
            b = intent_ids[i + 1] if i + 1 < len(intent_ids) else None
            pairs.append((a, b))
            i += 2

        matched_ids: list[int] = []

        raw_responses = run_coroutine_sync(
            _pair_check_raw_responses(
                pairs,
                subject,
                email_body,
                detected_concerns,
                history_summary,
                email_summary,
            )
        )

        for (a_id, b_id), raw in zip(pairs, raw_responses):
            data = parse_llm_json(raw)

            ids_this_pass: list[int] = []
            if isinstance(data, list):
                for x in data:
                    try:
                        x_i = int(x)
                        if x_i in (a_id, b_id):
                            ids_this_pass.append(x_i)
                    except Exception:
                        pass
            elif isinstance(data, dict):
                if bool(data.get("matches_a")):
                    ids_this_pass.append(a_id)
                if b_id and bool(data.get("matches_b")):
                    ids_this_pass.append(b_id)

            for x in ids_this_pass:
                if x not in matched_ids:
                    matched_ids.append(x)

        matched_ids = strip_false_not_interested_for_positive_relocation(
            matched_ids,
            body=email_body,
            concerns=detected_concerns,
            email_summary=email_summary,
        )

        if not matched_ids:
            matched_ids = [1]

        detected_intents = [
            {"intent_id": i_id, "intent_label": INTENT_BUCKETS.get(i_id, "Unknown")}
            for i_id in matched_ids
        ]
        primary_intent_id = matched_ids[0]
        primary_intent_label = INTENT_BUCKETS.get(primary_intent_id, "Unknown")

        state["detected_intents"] = detected_intents
        state["detected_intents_json"] = json.dumps(detected_intents, ensure_ascii=False)
        state["primary_intent_id"] = primary_intent_id
        state["primary_intent_label"] = primary_intent_label
        state["intent_id"] = primary_intent_id
        state["intent_label"] = primary_intent_label

    except LLMError:
        raise
    except Exception as e:
        logger.warning("[IntentClassifier] Parse error: %s", e)
        state["detected_intents"] = [{"intent_id": 1, "intent_label": INTENT_BUCKETS[1]}]
        state["detected_intents_json"] = json.dumps(state["detected_intents"], ensure_ascii=False)
        state["primary_intent_id"] = 1
        state["primary_intent_label"] = INTENT_BUCKETS[1]
        state["intent_id"] = 1
        state["intent_label"] = INTENT_BUCKETS[1]

    logger.info(
        "[IntentClassifier] primary_intent=%s (%s) | intents=%s",
        state.get("primary_intent_id", state.get("intent_id")),
        state.get("primary_intent_label", state.get("intent_label")),
        [x.get("intent_id") for x in state.get("detected_intents", []) or []],
    )
    return state
