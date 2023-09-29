from service.search_engine import find_phrase
import os
from service.data_dir import data_directory
from service.db import get_word_for_chat

if __name__ == "__main__":
    queries = get_word_for_chat(1)
    messages_directory = os.path.join(data_directory, "messages")

    for message in os.listdir(messages_directory):
        res = []
        fpath = os.path.join(data_directory, "messages", message)
        with open(fpath, 'r', encoding='utf-8') as file:
            text = file.read()
        for query in queries:
            results = find_phrase(query, text)
            if results > 50:
                res.append(f"   >> {query}: {results :.0f}%")
        if res:
            print("======================================")
            print(text)
            print("\n".join(res))
            print()
        else:
            print(f">>Removed\n"
                  f"{text}")
            os.remove(fpath)
