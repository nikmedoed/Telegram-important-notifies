from service.data_dir import data_directory
import os

with open(os.path.join(data_directory, "chats"), 'r', encoding="utf8") as f:
    _chats = set([int(i) for i in f.read().split() if i])

with open(os.path.join(data_directory, "queries"), 'r', encoding="utf8") as f:
    _queries = set(line.strip() for line in f if line.strip())


def get_chats():
    return _chats


def get_word_for_chat(chat_id):
    return _queries
