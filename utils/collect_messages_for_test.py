"""
Собирает потенциально релевантные сообщения для тестирования движка.
- Берём все запросы и каналы из базы.
- Строим объединённый набор токенов по запросам для канала.
- Проходим до 1000 последних сообщений канала, токенизируем и сохраняем те,
  где есть пересечение токенов.
"""
from hashlib import md5
from pathlib import Path
from typing import Dict, Iterable, Set

from service.config import client, data_directory
from service.db import db
from service.search_engine import tokenize
from service.text_cleaner import clean_text


def _collect_channel_tokens(queries: Iterable[str], tokens_map: Dict[str, list[str]] | None = None) -> Set[str]:
    tokens: Set[str] = set()
    for phrase in queries:
        if tokens_map and phrase in tokens_map:
            tokens.update(tokens_map[phrase])
        else:
            tokens.update(tokenize(phrase))
    return tokens


def _strip_metadata(text: str) -> str:
    lines = text.splitlines()
    while lines and lines[0].startswith(("chat_id:", "message_id:", "trigger_token:")):
        lines.pop(0)
    return clean_text("\n".join(lines))


def _load_existing_hashes(messages_dir: Path) -> Set[str]:
    hashes: Set[str] = set()
    if not messages_dir.exists():
        return hashes
    for file in messages_dir.glob("*.txt"):
        try:
            text = file.read_text(encoding="utf-8")
        except OSError:
            continue
        hashes.add(md5(_strip_metadata(text).encode("utf-8")).hexdigest())
    return hashes


def _save_message(path: Path, chat_id: int, message_id: int, trigger_token: str, message_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = f"chat_id:{chat_id}\nmessage_id:{message_id}\ntrigger_token:{trigger_token}\n{message_text}"
    path.write_text(payload, encoding="utf-8")


def main(limit_per_chat: int = 1000) -> None:
    messages_dir = Path(data_directory) / "messages"
    messages_dir.mkdir(parents=True, exist_ok=True)
    tracked_chats = db.get_tracked_chat_ids()
    if not tracked_chats:
        print("Нет каналов с запросами.")
        return

    existing_hashes = _load_existing_hashes(messages_dir)
    print(f"Трекнутых каналов: {len(tracked_chats)}")
    print(f"Уже сохранено уникальных сообщений: {len(existing_hashes)}")

    saved_total = 0
    skipped_duplicates = 0
    per_chat_saved: Dict[int, int] = {}

    for chat_id in tracked_chats:
        queries = db.get_queries_for_chat(chat_id)
        if not queries:
            continue

        channel_tokens = _collect_channel_tokens(
            queries,
            tokens_map=None,
        )
        if not channel_tokens:
            continue

        saved = 0
        for msg in client.iter_messages(chat_id, limit=limit_per_chat):
            if not msg or not getattr(msg, "text", None):
                continue
            cleaned_text = clean_text(msg.text)
            if not cleaned_text:
                continue
            msg_tokens = set(tokenize(cleaned_text))
            matched_tokens = msg_tokens & channel_tokens
            if not msg_tokens or not matched_tokens:
                continue

            message_hash = md5(cleaned_text.encode("utf-8")).hexdigest()
            if message_hash in existing_hashes:
                skipped_duplicates += 1
                continue

            fname = f"{message_hash}.txt"
            fpath = messages_dir / fname
            if fpath.exists():
                continue
            trigger_token = next(iter(matched_tokens))
            _save_message(fpath, chat_id, msg.id, trigger_token, cleaned_text)
            existing_hashes.add(message_hash)
            saved += 1
            saved_total += 1

        per_chat_saved[chat_id] = saved
        print(f"Канал {chat_id}: запросов {len(queries)}, сохранено {saved}")

    print(f"Итого сохранено сообщений: {saved_total}")
    if skipped_duplicates:
        print(f"Пропущено дубликатов по тексту: {skipped_duplicates}")


if __name__ == "__main__":
    main()
