"""Named local documents; legacy canvas is imported once without deleting it."""
import json
import time
import uuid
from .storage import StudioError, atomic_write


class Library:
    def __init__(self, store):
        self.store = store
        self.path = store.root / 'scripts.json'

    def read(self):
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding='utf-8'))
            except (ValueError, OSError):
                raise StudioError('脚本库无法读取，原文件已保留。') from None
        legacy = self.store.root / 'workspace.aircon.json'
        if legacy.exists():
            value = json.loads(legacy.read_text(encoding='utf-8'))
            value.update(id=uuid.uuid4().hex, name='原有脚本', mode='blocks', updated=time.time())
            self.write([value])
            return [value]
        return []

    def write(self, items):
        atomic_write(self.path, json.dumps(items, ensure_ascii=False, indent=2))

    def list(self):
        with self.store.lock:
            return [{k: item.get(k) for k in ('id', 'name', 'mode', 'updated')} for item in self.read()]

    def get(self, key):
        with self.store.lock:
            for item in self.read():
                if item['id'] == key:
                    return item
        raise StudioError('找不到这个脚本。')

    def save(self, data):
        name = str(data.get('name', '')).strip()
        if not name or len(name) > 100:
            raise StudioError('脚本名称必须是 1–100 个字符。')
        item = {k: data[k] for k in ('workspace', 'code', 'mode') if k in data}
        item.update(format='HallAirconStudio', version=1, id=data.get('id') or uuid.uuid4().hex, name=name, updated=time.time())
        if item.get('mode', 'blocks') not in ('blocks', 'code') or len(json.dumps(item)) > 1_000_000:
            raise StudioError('脚本模式无效或超过 1MB。')
        with self.store.lock:
            items = self.read()
            items = [old for old in items if old['id'] != item['id']]
            items.append(item)
            self.write(items)
        return item

    def delete(self, key):
        with self.store.lock:
            self.write([item for item in self.read() if item['id'] != key])

