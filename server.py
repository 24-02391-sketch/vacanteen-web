import os
import json
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

class BSTNode:
    def __init__(self, sr_code):
        self.sr_code = sr_code
        self.left = None
        self.right = None

class SRCodeBST:
    def __init__(self):
        self.root = None
    def insert(self, root, sr_code):
        if root is None: return BSTNode(sr_code)
        if sr_code < root.sr_code: root.left = self.insert(root.left, sr_code)
        elif sr_code > root.sr_code: root.right = self.insert(root.right, sr_code)
        return root
    def search(self, root, sr_code):
        if root is None or root.sr_code == sr_code: return root
        if root.sr_code < sr_code: return self.search(root.right, sr_code)
        return self.search(root.left, sr_code)

active_students_bst = SRCodeBST()

class SessionMinHeap:
    def __init__(self):
        self.heap = []
    def parent(self, i): return (i - 1) // 2
    def insert(self, session):
        self.heap.append(session)
        self._heapify_up(len(self.heap) - 1)
    def _heapify_up(self, i):
        while i != 0 and self.heap[self.parent(i)]['expire_time'] > self.heap[i]['expire_time']:
            self.heap[i], self.heap[self.parent(i)] = self.heap[self.parent(i)], self.heap[i]
            i = self.parent(i)

active_sessions_heap = SessionMinHeap()

class VaCanteenServer(BaseHTTPRequestHandler):
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

    def do_POST(self):
        if self.path == '/api/checkin':
            content_length = int(self.headers['Content-Length'])
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))

            sr_code = data.get('sr_code')
            table_id = data.get('table_id')

            if active_students_bst.search(active_students_bst.root, sr_code):
                response = {"status": "error", "message": f"SR Code {sr_code} is already seated!"}
                self.send_response(400)
            else:
                active_students_bst.root = active_students_bst.insert(active_students_bst.root, sr_code)
                active_sessions_heap.insert({
                    "sr_code": sr_code,
                    "table_id": table_id,
                    "expire_time": time.time() + 60
                })
                response = {"status": "success"}
                self.send_response(200)

            self.send_header('Content-type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps(response).encode('utf-8'))

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8000))
    server = HTTPServer(('0.0.0.0', port), VaCanteenServer)
    print(f"Server running on port {port}")
    server.serve_forever()