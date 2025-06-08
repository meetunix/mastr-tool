import pickle
from pathlib import Path
from threading import RLock
from typing import Any, Union


class Cache:
    """
    A general-purpose caching class.

    Features:
    - Simple key-value storage
    - Thread-safe operations
    - Configurable maximum size
    - Persistence through pickle serialization
    """

    def __init__(self, max_size=2**32):
        """
        Initialize the cache.

        Args:
            max_size (int): Maximum number of items to store in the cache, default: 2^32
        """
        self._cache = {}
        self._max_size = max_size
        self._lock = RLock()

    def get(self, key, default=None) -> Any:
        """
        Retrieve an item from the cache.

        Args:
            key: The key to look up
            default: Value to return if key is not found

        Returns:
            The cached value or default if not found
        """
        with self._lock:
            return self._cache.get(key, default)

    def set(self, key, value) -> bool:
        """
        Add an item to the cache.

        Args:
            key: The key to store the value under
            value: The value to cache

        Returns:
            bool: False if cache is full and key doesn't exist, True otherwise
        """
        with self._lock:
            # If we're at capacity and this is a new key, reject the addition
            if len(self._cache) >= self._max_size and key not in self._cache:
                return False

            # Add to the cache
            self._cache[key] = value
            return True

    def delete(self, key) -> bool:
        """
        Remove an item from the cache.

        Args:
            key: The key to remove

        Returns:
            bool: True if the key was found and removed, False otherwise
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """Clear all items from the cache."""
        with self._lock:
            self._cache.clear()

    def __contains__(self, key) -> bool:
        """Check if a key exists in the cache."""
        with self._lock:
            return key in self._cache

    def __len__(self) -> int:
        """Return the number of items in the cache."""
        with self._lock:
            return len(self._cache)

    def keys(self) -> list:
        """Return a list of all keys in the cache."""
        with self._lock:
            return list(self._cache.keys())

    def store(self, file_path: Union[str, Path]) -> None:
        """
        Serialize and save the cache to disk.

        Args:
            :param file_path:  Path to store the cache file at.

        """
        with self._lock:
            try:
                if isinstance(file_path, str):
                    file_path = Path(file_path)

                file_path = Path(file_path)
                file_path.parent.mkdir(parents=True, exist_ok=True)

                with open(file_path, "wb") as file:
                    # store the cache contents and max_size
                    # but not the lock as it's not serializable
                    data = {"cache": self._cache, "max_size": self._max_size}
                    pickle.dump(data, file)  # type: ignore
            except (IOError, pickle.PickleError) as e:
                print(f"Error storing cache: {e}")

    @classmethod
    def load(cls, filepath: Union[str, Path] = None):
        """
        Load a cache from the filesystem.

        Args:
            filepath (str): Path to the stored cache file

        Returns:
            Cache: A new Cache instance with the loaded data, or new Cache if loading failed
        """
        try:
            if filepath is None:
                return cls()

            if isinstance(filepath, str):
                filepath = Path(filepath)

            if not filepath.exists() or not filepath.is_file():
                return cls()

            with open(filepath, "rb") as f:
                data = pickle.load(f)

            # Create a new cache instance
            cache = cls(max_size=data["max_size"])

            # Populate with loaded data
            cache._cache = data["cache"]

            return cache
        except (IOError, pickle.PickleError, KeyError) as e:
            print(f"Error loading cache: {e}")
            return None
