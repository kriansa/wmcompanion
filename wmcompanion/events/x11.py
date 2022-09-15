import asyncio, json, logging
from pathlib import Path
from ..event_listening import EventListener
from ..utils.process import ProcessWatcher
from ..errors import WMCompanionFatalError

logger = logging.getLogger(__name__)

class ScreenState(EventListener):
    async def start(self):
        cmd = ["python", Path(__file__).parent.joinpath("x11_screen_watcher.py")]
        pw = ProcessWatcher(cmd, restart_every=3600)
        pw.on_start(self.read_events)
        pw.on_failure(self.on_failure)
        await pw.start()

    async def read_events(self, proc):
        while line := await proc.stdout.readline():
            action = json.loads(line.decode("utf-8"))
            if action["action"] == "event":
                await self.trigger({ "screens": action["event"] })
            elif action["action"] == "error":
                logger.error("X11 screen watcher error: " + "".join(action["error"]))

    async def on_failure(self):
        raise WMCompanionFatalError("x11_screen_watcher.py initialization failed")
