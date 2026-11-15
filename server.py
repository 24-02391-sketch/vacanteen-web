import os
import re
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

STATE_FILE = 'canteen_state.json'
SR_CODE_PATTERN = re.compile(r'^\d{2}-\d{5}$')
ACCESS_PASSWORD = 'batstateu'
REGULAR_AUTO_EXPIRE_SECONDS = 21 * 60  # 20 mins + 60s "Are you still there?" grace period


def is_valid_sr_code(sr_code):
    if not isinstance(sr_code, str):
        return False
    sr_code = sr_code.strip()
    return bool(SR_CODE_PATTERN.match(sr_code)) and sr_code != '00-00000'


class BSTNode:
    def __init__(self, sr_code):
        self.sr_code = sr_code
        self.left = None
        self.right = None


class SRCodeBST:
    def __init__(self):
        self.root = None

    def insert(self, root, sr_code):
        if root is None:
            return BSTNode(sr_code)
        if sr_code < root.sr_code:
            root.left = self.insert(root.left, sr_code)
        elif sr_code > root.sr_code:
            root.right = self.insert(root.right, sr_code)
        return root

    def search(self, root, sr_code):
        if root is None or root.sr_code == sr_code:
            return root
        if root.sr_code < sr_code:
            return self.search(root.right, sr_code)
        return self.search(root.left, sr_code)

    def delete(self, root, sr_code):
        if root is None:
            return root
        if sr_code < root.sr_code:
            root.left = self.delete(root.left, sr_code)
        elif sr_code > root.sr_code:
            root.right = self.delete(root.right, sr_code)
        else:
            if root.left is None:
                return root.right
            elif root.right is None:
                return root.left
            temp = self._min_value_node(root.right)
            root.sr_code = temp.sr_code
            root.right = self.delete(root.right, temp.sr_code)
        return root

    def _min_value_node(self, node):
        current = node
        while current.left is not None:
            current = current.left
        return current


active_students_bst = SRCodeBST()


class SessionMinHeap:
    def __init__(self):
        self.heap = []

    def parent(self, i):
        return (i - 1) // 2

    def insert(self, session):
        self.heap.append(session)
        self._heapify_up(len(self.heap) - 1)

    def _heapify_up(self, i):
        while i != 0 and self.heap[self.parent(i)]['expire_time'] > self.heap[i]['expire_time']:
            self.heap[i], self.heap[self.parent(i)] = self.heap[self.parent(i)], self.heap[i]
            i = self.parent(i)

    def _heapify_down(self, i):
        smallest = i
        left = 2 * i + 1
        right = 2 * i + 2
        if left < len(self.heap) and self.heap[left]['expire_time'] < self.heap[smallest]['expire_time']:
            smallest = left
        if right < len(self.heap) and self.heap[right]['expire_time'] < self.heap[smallest]['expire_time']:
            smallest = right
        if smallest != i:
            self.heap[i], self.heap[smallest] = self.heap[smallest], self.heap[i]
            self._heapify_down(smallest)

    def remove_by_id(self, session_id):
        for idx, s in enumerate(self.heap):
            if s.get('id') == session_id:
                last = self.heap.pop()
                if idx < len(self.heap):
                    self.heap[idx] = last
                    self._heapify_up(idx)
                    self._heapify_down(idx)
                return s
        return None

    def update_expire_by_id(self, session_id, new_expire_time, new_confirmed_ms):
        for idx, s in enumerate(self.heap):
            if s.get('id') == session_id:
                s['expire_time'] = new_expire_time
                s['lastConfirmedAt'] = new_confirmed_ms
                self._heapify_up(idx)
                self._heapify_down(idx)
                return s
        return None


active_sessions_heap = SessionMinHeap()


def save_state():
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(active_sessions_heap.heap, f)
    except Exception as e:
        print("Save error:", e)


def load_state():
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE, 'r', encoding='utf-8') as f:
            saved_sessions = json.load(f)
        for s in saved_sessions:
            sr = s.get('srCode')
            if sr:
                active_students_bst.root = active_students_bst.insert(active_students_bst.root, sr)
            active_sessions_heap.insert(s)
    except Exception as e:
        print("Load error:", e)


def cleanup_expired():
    now = time.time()
    expired_ids = [s['id'] for s in active_sessions_heap.heap if s.get('expire_time', 9999999999) <= now]
    for sid in expired_ids:
        removed = active_sessions_heap.remove_by_id(sid)
        if removed and removed.get('srCode'):
            active_students_bst.root = active_students_bst.delete(active_students_bst.root, removed['srCode'])
    if expired_ids:
        save_state()


def get_taken_seats(table_id):
    taken = set()
    for s in active_sessions_heap.heap:
        if s.get('tableId') == table_id:
            seat_nums = s.get('selectedSeatNumbers') or []
            if seat_nums:
                taken.update(seat_nums)
            else:
                taken.update(range(1, int(s.get('seats', 0)) + 1))
    return taken


load_state()


class VaCanteenServer(BaseHTTPRequestHandler):
    def _send_json(self, code, payload):
        self.send_response(code)
        self.send_header('Content-type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps(payload).encode('utf-8'))

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            try:
                with open('VaCanteen Frontend.html', 'rb') as file:
                    self.wfile.write(file.read())
            except FileNotFoundError:
                self.wfile.write(b"Error: 'VaCanteen Frontend.html' not found.")
        elif self.path == '/api/state':
            cleanup_expired()
            self._send_json(200, {"sessions": active_sessions_heap.heap})
        elif self.path == '/favicon.ico':
            self.send_response(204)
            self.end_headers()
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        content_length = int(self.headers.get('Content-Length', 0))
        post_data = self.rfile.read(content_length)
        data = json.loads(post_data.decode('utf-8')) if post_data else {}

        if self.path == '/api/checkin':
            cleanup_expired()
            sr_code = (data.get('sr_code') or '').strip()
            password = (data.get('password') or '').strip()
            table_id = data.get('table_id')
            party = int(data.get('party', 1))

            if password != ACCESS_PASSWORD:
                self._send_json(401, {
                    "status": "error",
                    "message": "Incorrect canteen access password."
                })
                return

            if not is_valid_sr_code(sr_code):
                self._send_json(400, {
                    "status": "error",
                    "message": "Invalid SR Code format. Use XX-XXXXX (e.g. 24-12345)."
                })
                return

            if active_students_bst.search(active_students_bst.root, sr_code):
                self._send_json(400, {
                    "status": "error",
                    "message": f"SR Code {sr_code} is already seated!"
                })
                return

            taken = get_taken_seats(table_id)
            if 6 - len(taken) < party:
                self._send_json(400, {
                    "status": "error",
                    "message": "Not enough available seats at this table."
                })
                return

            self._send_json(200, {"status": "success"})

        elif self.path == '/api/seat':
            cleanup_expired()
            sr_code = (data.get('srCode') or '').strip()
            password = (data.get('password') or '').strip()
            table_id = data.get('tableId')
            seat_numbers = [int(x) for x in (data.get('selectedSeatNumbers') or [])]

            if password != ACCESS_PASSWORD:
                self._send_json(401, {
                    "status": "error",
                    "message": "Incorrect canteen access password."
                })
                return

            if not is_valid_sr_code(sr_code):
                self._send_json(400, {
                    "status": "error",
                    "message": "Invalid SR Code format. Use XX-XXXXX (e.g. 24-12345)."
                })
                return

            if active_students_bst.search(active_students_bst.root, sr_code):
                self._send_json(400, {
                    "status": "error",
                    "message": f"SR Code {sr_code} is already seated!"
                })
                return

            taken = get_taken_seats(table_id)
            if any(s in taken or s < 1 or s > 6 for s in seat_numbers):
                self._send_json(400, {
                    "status": "error",
                    "message": "One or more selected seats were just taken. Please pick again."
                })
                return

            duration = int(data.get('duration', 0))
            started_ms = data.get('startedAt', int(time.time() * 1000))
            started_sec = started_ms / 1000.0
            expire_time = (started_sec + duration * 60) if duration > 0 else (started_sec + REGULAR_AUTO_EXPIRE_SECONDS)

            session_record = {
                "id": data.get('id'),
                "srCode": sr_code,
                "tableId": table_id,
                "seats": len(seat_numbers) if seat_numbers else int(data.get('seats', 1)),
                "selectedSeatNumbers": sorted(seat_numbers),
                "startedAt": started_ms,
                "lastConfirmedAt": started_ms,
                "duration": duration,
                "seated": True,
                "expire_time": expire_time
            }

            active_students_bst.root = active_students_bst.insert(active_students_bst.root, sr_code)
            active_sessions_heap.insert(session_record)
            save_state()
            self._send_json(200, {"status": "success"})

        elif self.path == '/api/keepalive':
            session_id = data.get('id')
            now_ms = int(time.time() * 1000)
            new_expire = time.time() + REGULAR_AUTO_EXPIRE_SECONDS
            updated = active_sessions_heap.update_expire_by_id(session_id, new_expire, now_ms)
            if updated:
                save_state()
                self._send_json(200, {"status": "success", "lastConfirmedAt": now_ms})
            else:
                self._send_json(404, {"status": "error", "message": "Session already expired."})

        elif self.path == '/api/leave':
            session_id = data.get('id')
            removed = active_sessions_heap.remove_by_id(session_id)
            sr_code = (removed.get('srCode') if removed else None) or data.get('sr_code')
            if sr_code:
                active_students_bst.root = active_students_bst.delete(active_students_bst.root, sr_code)
            save_state()
            self._send_json(200, {"status": "success"})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), VaCanteenServer)
    print(f"Server running on port {port}")
    server.serve_forever()