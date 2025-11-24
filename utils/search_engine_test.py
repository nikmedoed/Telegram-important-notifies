"""
Прогоняет собранные сообщения через текущий поисковый движок.
- Берёт все запросы по каждому каналу (из базы).
- Файлы формата data/messages/<hash>.txt, внутри первые строки chat_id / message_id / trigger_token.
- Считает статистику по срабатываниям и сохраняет отчёт в Markdown.
"""
from collections import Counter, defaultdict
from pathlib import Path
from typing import Dict, List, Tuple

from service import search_engine as se
from service.config import data_directory
from service.db import db
from service.text_cleaner import clean_text

MESSAGES_DIR = Path(data_directory) / "messages"
SCORE_DISPLAY_THRESHOLD = 30
MATCH_THRESHOLD = 55

channel_cache: Dict[int, str] = {}
query_meta_cache: Dict[int, Dict[str, object]] = {}


def _extract_metadata(text: str) -> Tuple[int | None, int | None, str | None, str]:
    chat_id = message_id = None
    trigger_token = None
    rest = text
    if rest.startswith("chat_id:"):
        first_line, _, rest = rest.partition("\n")
        try:
            chat_id = int(first_line.split(":", 1)[1].strip())
        except (ValueError, IndexError):
            chat_id = None
    if rest.startswith("message_id:"):
        first_line, _, rest = rest.partition("\n")
        try:
            message_id = int(first_line.split(":", 1)[1].strip())
        except (ValueError, IndexError):
            message_id = None
    if rest.startswith("trigger_token:"):
        first_line, _, rest = rest.partition("\n")
        trigger_token = first_line.split(":", 1)[1].strip()
    return chat_id, message_id, trigger_token, clean_text(rest)


def _get_channel_title(chat_id: int) -> str:
    if chat_id in channel_cache:
        return channel_cache[chat_id]
    record = db.get_channel(chat_id)
    if record:
        title = record.title or f"Chat {chat_id}"
    else:
        title = str(chat_id)
    channel_cache[chat_id] = title
    return title


def _is_full_match(scores: Dict[str, float]) -> bool:
    if not scores:
        return False
    return all(round(value, 2) >= 99.99 for value in scores.values())


def _get_query_meta(chat_id: int, queries: Tuple[str, ...]) -> Dict[str, object]:
    cached = query_meta_cache.get(chat_id)
    if cached and cached.get("queries") == queries:
        return cached
    specs = {}
    for query in queries:
        tokens, clauses = se.parse_query_phrase(query)
        if not clauses:
            continue
        specs[query] = {"tokens": tokens, "clauses": clauses}
    idf_map = se._build_idf((meta["tokens"] for meta in specs.values()))
    tfidf_map = {
        query: tuple(se._tfidf_vector(clause.tokens, idf_map) for clause in meta["clauses"])
        for query, meta in specs.items()
    }
    data = {"queries": queries, "specs": specs, "idf": idf_map, "tfidf": tfidf_map}
    query_meta_cache[chat_id] = data
    return data


def _score_queries(meta: Dict[str, object], text: str) -> Dict[str, float]:
    scores: Dict[str, float] = {}
    idf_map = meta["idf"]
    specs = meta["specs"]
    tfidf_map = meta["tfidf"]
    for query, meta_entry in specs.items():
        clauses = meta_entry["clauses"]
        clause_vectors = tfidf_map.get(query, ())
        clause_scores = []
        for idx, clause in enumerate(clauses):
            vec, norm = clause_vectors[idx] if idx < len(clause_vectors) else se._tfidf_vector(clause.tokens, idf_map)
            score = se.find_phrase(
                query,
                text,
                query_tokens=clause.tokens,
                idf_map=idf_map,
                query_tfidf=vec,
                query_norm=norm,
                required_tokens=clause.required,
            )
            clause_scores.append(score)
        if clause_scores:
            scores[query] = min(clause_scores)
    return scores


def _format_score_lines(scores: Dict[str, float], threshold: float) -> List[str]:
    filtered = sorted(((q, s) for q, s in scores.items() if s >= threshold), key=lambda x: -x[1])
    if not filtered:
        return [f"- Query scores: _< {threshold:.0f}%_"]
    lines = ["- Query scores:"]
    for query, score in filtered:
        lines.append(f"  - {query}: {score:.0f}%")
    return lines


def _append_message_block(
    lines: List[str],
    title: str,
    message_id: int,
    trigger_token: str | None,
    text: str,
    scores: Dict[str, float],
) -> None:
    add = lines.append
    add("")
    add(f"### {title} — message {message_id}")
    if trigger_token:
        add("")
        add(f"- Trigger token: `{trigger_token}`")
    add("")
    add("\n".join(_format_score_lines(scores, SCORE_DISPLAY_THRESHOLD)))
    add("")
    add("```")
    add(text.strip())
    add("```")


def main() -> None:
    if not MESSAGES_DIR.exists():
        print(f"Каталог с сообщениями не найден: {MESSAGES_DIR}")
        return

    total = matched = 0
    per_chat = defaultdict(lambda: {"total": 0, "matched": 0})
    query_hits: Counter[str] = Counter()
    matched_messages: List[Tuple[int, int, str | None, str, Dict[str, float], Dict[str, float]]] = []
    unmatched_messages: List[Tuple[int, int, str | None, str, Dict[str, float]]] = []
    all_queries_records = db.list_queries()
    all_queries_ordered = [record.phrase for record in all_queries_records]

    files = sorted(MESSAGES_DIR.glob("*.txt"))
    if not files:
        print("Нет сообщений для теста.")
        return

    for file in files:
        raw = file.read_text(encoding="utf-8")
        chat_id, message_id, trigger_token, text = _extract_metadata(raw)
        if chat_id is None or message_id is None:
            print(f"Пропуск файла {file.name} (нет chat_id или message_id)")
            continue
        queries = tuple(db.get_queries_for_chat(chat_id))
        if not queries:
            print(f"Нет запросов для канала {chat_id}, сообщение {message_id} пропущено.")
            continue

        total += 1
        per_chat[chat_id]["total"] += 1

        meta = _get_query_meta(chat_id, queries)
        raw_scores = _score_queries(meta, text)
        display_scores = {q: round(score, 2) for q, score in raw_scores.items()}
        matched_scores = {q: score for q, score in display_scores.items() if score >= MATCH_THRESHOLD}

        if matched_scores:
            matched += 1
            per_chat[chat_id]["matched"] += 1
            for q in matched_scores:
                query_hits[q] += 1
            matched_messages.append((chat_id, message_id, trigger_token, text, display_scores, matched_scores))
        else:
            unmatched_messages.append((chat_id, message_id, trigger_token, text, display_scores))

    report_path = Path(data_directory) / "search_engine_report.md"
    old_report = report_path.with_suffix(".prev.md")
    if report_path.exists():
        if old_report.exists():
            old_report.unlink()
        report_path.rename(old_report)

    lines: List[str] = []
    add = lines.append

    add("# Search Engine Test Report")
    add("")
    add("## Summary")
    add("")
    add(f"- Processed: **{total}**")
    add(f"- Matched: **{matched}**")
    add(f"- Unmatched (skipped): **{total - matched}**")
    add("")

    add("## Per Channel")
    add("")
    add("| Channel | Total | Matched | Unmatched | Hit Rate |")
    add("| --- | --- | --- | --- | --- |")
    for chat_id, data in sorted(per_chat.items()):
        hit = data["matched"]
        total_chat = data["total"]
        miss = total_chat - hit
        hit_rate = (100 * hit / total_chat) if total_chat else 0
        channel_label = _get_channel_title(chat_id)
        add(f"| {channel_label} | {total_chat} | {hit} | {miss} | {hit_rate:.1f}% |")
    if not per_chat:
        add("| – | 0 | 0 | 0 | 0% |")
    add("")

    add("## Top Queries")
    add("")
    if not all_queries_ordered:
        add("- Нет запросов в базе.")
    else:
        for query in all_queries_ordered:
            cnt = query_hits.get(query, 0)
            add(f"- **{query}**: {cnt}")
    add("")

    add("## Unmatched Messages")
    if not unmatched_messages:
        add("")
        add("_All messages matched._")
    else:
        for chat_id, message_id, trigger_token, text, scores in unmatched_messages:
            _append_message_block(
                lines,
                _get_channel_title(chat_id),
                message_id,
                trigger_token,
                text,
                scores,
            )

    partial_matches = []
    exact_matches = []
    for entry in matched_messages:
        _, _, _, _, _, matched_scores = entry
        if _is_full_match(matched_scores):
            exact_matches.append(entry)
        else:
            partial_matches.append(entry)

    add("")
    add("## Partial Matches (<100%)")
    if not partial_matches:
        add("")
        add("_Нет частичных совпадений._")
    else:
        for chat_id, message_id, trigger_token, text, scores, _ in partial_matches:
            _append_message_block(
                lines,
                _get_channel_title(chat_id),
                message_id,
                trigger_token,
                text,
                scores,
            )

    add("")
    add("## Exact Matches (100%)")
    if not exact_matches:
        add("")
        add("_Нет полных совпадений._")
    else:
        for chat_id, message_id, trigger_token, text, scores, _ in exact_matches:
            _append_message_block(
                lines,
                _get_channel_title(chat_id),
                message_id,
                trigger_token,
                text,
                scores,
            )

    report_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"Отчёт сохранён: {report_path}")


if __name__ == "__main__":
    main()
