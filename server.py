import os
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

STATE_FILE = 'canteen_state.json'

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
            sr_code = data.get('sr_code')
            if active_students_bst.search(active_students_bst.root, sr_code):
                self._send_json(400, {"status": "error", "message": f"SR Code {sr_code} is already seated!"})
            else:
                self._send_json(200, {"status": "success"})

        elif self.path == '/api/seat':
            sr_code = data.get('srCode')
            if sr_code and active_students_bst.search(active_students_bst.root, sr_code):
                self._send_json(400, {"status": "error", "message": f"SR Code {sr_code} is already seated!"})
                return

            duration = int(data.get('duration', 0))
            started_sec = data.get('startedAt', time.time() * 1000) / 1000.0
            expire_time = (started_sec + duration * 60) if duration > 0 else 9999999999

            session_record = {
                "id": data.get('id'),
                "srCode": sr_code,
                "tableId": data.get('tableId'),
                "seats": data.get('seats'),
                "selectedSeatNumbers": data.get('selectedSeatNumbers', []),
                "startedAt": data.get('startedAt'),
                "duration": duration,
                "seated": True,
                "expire_time": expire_time
            }

            if sr_code:
                active_students_bst.root = active_students_bst.insert(active_students_bst.root, sr_code)
            active_sessions_heap.insert(session_record)
            save_state()
            self._send_json(200, {"status": "success"})

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