import threading
import time

DEFAULLT_TTL = 60*60*24

class Cache:
    def __init__(self):
        self.cache = {}
        self.lock = threading.Lock()
        cleanup_thread = threading.Thread(target=self.cleanup, daemon=True)
        cleanup_thread.start()

    def set(self, key, value, ttl=DEFAULLT_TTL):
        with self.lock:
            self.cache[key] = (value, time.time() + ttl)

    def get(self, key):
        with self.lock:
            if key in self.cache and self.cache[key][1] >= time.time():
                return self.cache[key][0]
            return None

    def delete(self, key):
        with self.lock:
            if key in self.cache:
                del self.cache[key]

    def cleanup(self):
        while True:
            with self.lock:
                current_time = time.time()
                expired_keys = [key for key, (_, expiry) in self.cache.items() if expiry < current_time]
                for key in expired_keys:
                    del self.cache[key]
            time.sleep(max(0.5, DEFAULLT_TTL / 30))  # Проверка каждую минуту на истекшие записи

    def __str__(self):
        return str(self.cache)


cache = Cache()

if __name__ == "__main__":
    # Пример использования
    cache.set('key1', 'value1', ttl=DEFAULLT_TTL)  # Запись будет жить 30 минут (1800 секунд)
    print(cache)
    cache.set('key2', 'value2', ttl=DEFAULLT_TTL * 2)  # Запись будет жить 60 минут (3600 секунд)
    print(cache)

    for i in range(5):
        print(cache.get('key1'))  # Выведет None, так как запись истекла
        print(cache.get('key2'))  # Выведет 'value1'
        print(cache)
        time.sleep(DEFAULLT_TTL + 1)  # Подождать больше 30 минут (для проверки истечения срока жизни записи)
