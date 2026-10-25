import {init, MGRS} from "../dist/browser.js";
self.onmessage = async () => {
  try {
    await init();
    const m = new MGRS();
    try {
      let code;
      for (let i = 0; i < 1000; i++) code = m.toMGRS(42, -93);
      self.postMessage(code);
    } finally { m.free(); }
  } catch (error) { self.postMessage({error: error.message}); }
};
