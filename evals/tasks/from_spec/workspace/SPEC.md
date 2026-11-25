# LRUキャッシュ

`lru.py` にクラス `LRUCache` を実装する。標準ライブラリだけを使う。

- `LRUCache(capacity)`: `capacity` は最大件数。1未満なら `ValueError`。
- `get(key, default=None)`: 値を返す。無ければ `default`。見つかったキーは「最近使った」扱いになる。
- `put(key, value)`: 追加または更新する。更新も「最近使った」扱いになる。
  件数が `capacity` を超えたら、最も長く使われていないキーを1件削除する。
- `keys()`: 最近使った順(新しいものが先頭)のキーのリスト。呼び出しても順序は変わらない。
- `len(cache)`: 現在の件数。
