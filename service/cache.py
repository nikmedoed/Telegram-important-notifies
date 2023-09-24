import threading
import time

DEFAULLT_TTL = 60 * 60 * 24


class Cache:
    """
    A thread-safe caching class that stores key-value pairs for a specified duration.

    Attributes:
        ttl (int): The default time-to-live (TTL) duration for cache entries in seconds.
    """

    ttl = DEFAULLT_TTL

    def __init__(self, ttl: int = None):
        """
        Initializes the Cache object.

        Args:
            ttl (int, optional): The default TTL for cache entries. If not provided, uses the class-level ttl.
        """
        if ttl:
            self.ttl = ttl
        self.cache = {}
        self.lock = threading.Lock()
        cleanup_thread = threading.Thread(target=self.cleanup, daemon=True)
        cleanup_thread.start()

    def set(self, key, value, ttl=None):
        """
        Adds a key-value pair to the cache with an optional TTL.

        Args:
            key: The key for the cache entry.
            value: The value to be stored.
            ttl (int, optional): The TTL for this cache entry. If not provided, uses the default ttl.
        """
        if not ttl:
            ttl = self.ttl
        with self.lock:
            self.cache[key] = (value, time.time() + ttl)

    def get(self, key):
        """
        Retrieves the value associated with the given key from the cache.

        Args:
            key: The key for the cache entry.

        Returns:
            The value associated with the key if it exists and hasn't expired, otherwise None.
        """
        with self.lock:
            if key in self.cache and self.cache[key][1] >= time.time():
                return self.cache[key][0]
            return None

    def delete(self, key):
        """
        Removes the cache entry associated with the given key.

        Args:
            key: The key for the cache entry.
        """
        with self.lock:
            if key in self.cache:
                del self.cache[key]

    def cleanup(self):
        """
        Periodically checks and removes expired cache entries.
        """
        while True:
            with self.lock:
                current_time = time.time()
                expired_keys = [key for key, (_, expiry) in self.cache.items() if expiry < current_time]
                for key in expired_keys:
                    del self.cache[key]
            time.sleep(max(0.5, self.ttl / 30))

    def __str__(self):
        """
        Returns a string representation of the cache.

        Returns:
            str: A string representation of the cache.
        """
        return str(self.cache)


if __name__ == "__main__":
    TIME = 10
    cache = Cache(TIME)
    cache.set('key1', 'value1')
    print(cache)
    cache.set('key2', 'value2', ttl=TIME * 2)
    print(cache)

    for i in range(5):
        print(cache.get('key1'))
        print(cache.get('key2'))
        print(cache)
        time.sleep(TIME + 1)
        print(f"\t>> +{TIME + 1} sec")
