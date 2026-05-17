import { Worker } from "@notionhq/workers";

import { registerIngestEvent } from "./tools/ingest-event.js";

const worker = new Worker();
export default worker;

registerIngestEvent(worker);
