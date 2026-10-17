import io
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

import server


class Regressions(unittest.TestCase):
    def test_media_boundary_and_symlink(self):
        with tempfile.TemporaryDirectory() as d:
            root = os.path.join(d, 'output')
            other = os.path.join(d, 'output-private')
            os.makedirs(root)
            os.makedirs(other)
            with patch.object(server, 'SETTINGS', {'output_dir': root}):
                self.assertIsNone(server.resolve_media('../output-private/secret.png'))
                self.assertEqual(server.resolve_media('image.png'), os.path.realpath(os.path.join(root, 'image.png')))
                os.symlink(other, os.path.join(root, 'link'))
                self.assertIsNone(server.resolve_media('link/secret.png'))

    def test_concurrent_runs_preserve_additions_and_updates(self):
        with tempfile.TemporaryDirectory() as d, patch.object(server, 'RUNS_FILE', os.path.join(d, 'runs.json')):
            with ThreadPoolExecutor(max_workers=8) as pool:
                list(pool.map(lambda i: server.add_run({'prompt_id': str(i)}), range(40)))
                list(pool.map(lambda i: server.update_run(str(i), done=True), range(40)))
            runs = server.load_runs()
            self.assertEqual(len(runs), 40)
            self.assertTrue(all(r['done'] for r in runs))
            self.assertEqual(os.listdir(d), ['runs.json'])

    def test_ranges(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, 'video.mp4')
            with open(path, 'wb') as f:
                f.write(b'0123456789')
            for request, status, expected, content_range in [
                ('bytes=-4', 206, b'6789', 'bytes 6-9/10'),
                ('bytes=3-', 206, b'3456789', 'bytes 3-9/10'),
                ('bytes=2-4', 206, b'234', 'bytes 2-4/10'),
                ('bytes=-20', 206, b'0123456789', 'bytes 0-9/10'),
                ('bytes=10-', 416, b'', 'bytes */10'),
                ('bytes=5-2', 416, b'', 'bytes */10'),
                ('bytes=-0', 416, b'', 'bytes */10'),
            ]:
                with self.subTest(request=request):
                    h = object.__new__(server.Handler)
                    h.wfile = io.BytesIO()
                    headers = {}
                    h.send_response = lambda code: headers.update(status=code)
                    h.send_header = lambda k, v: headers.update({k: v})
                    h.end_headers = lambda: None
                    h.send_file(path, 'video/mp4', ranges=request)
                    self.assertEqual(headers['status'], status)
                    self.assertEqual(headers['Content-Range'], content_range)
                    self.assertEqual(h.wfile.getvalue(), expected)
                    self.assertEqual(int(headers['Content-Length']), len(expected))

    def test_settings_switch_client_and_clear_schema_cache(self):
        settings = dict(server.DEFAULT_SETTINGS)
        old = server.ComfyClient(settings['comfy_url'])
        old.object_info_cache = {'old': {}}
        h = object.__new__(server.Handler)
        h.send_json = lambda obj: obj
        with patch.object(server, 'SETTINGS', settings), patch.object(server, 'COMFY', old), patch.object(server, 'save_settings'):
            result = h.api('POST', '/api/settings', {}, {'comfy_url': 'http://127.0.0.1:9999/'})
            self.assertTrue(result['ok'])
            self.assertEqual(server.COMFY.base, 'http://127.0.0.1:9999')
            self.assertIsNone(server.COMFY.object_info_cache)
            current = server.COMFY
            h.api('POST', '/api/settings', {}, {'gallery_cap': 20})
            self.assertIs(server.COMFY, current)

    def test_websocket_close_releases_socket_after_shutdown(self):
        from unittest.mock import Mock
        ws = server.MiniWS('ws://127.0.0.1/ws')
        ws.sock = Mock()
        ws.sock.sendall.side_effect = OSError('socket shut down')
        ws.close()
        ws.sock.close.assert_called_once()
        self.assertFalse(ws.alive)
