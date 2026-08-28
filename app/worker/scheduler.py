from __future__ import annotations
import threading,time,random,logging
log=logging.getLogger(__name__)
class ProactiveScheduler:
    def __init__(self,callback):self.callback=callback; self._stop=threading.Event(); self._thread=None
    def start(self):
        if self._thread and self._thread.is_alive():return
        self._thread=threading.Thread(target=self._run,daemon=True,name="kyoos-proactive"); self._thread.start()
    def stop(self):self._stop.set()
    def _run(self):
        while not self._stop.wait(random.uniform(25,50)):
            try:self.callback()
            except Exception:log.exception("proactive scheduler failure")
