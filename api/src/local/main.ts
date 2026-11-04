// Run the local chat API (#101):  cd api && npx --yes tsx@4.19.2 src/local/main.ts
// FEX_AGENT_URL (default http://127.0.0.1:8080) is the agent from agent/scripts/serve_local.py.
import { HttpAgentClient } from './agentClient.js';
import { createLocalServer } from './server.js';

const agentUrl = process.env.FEX_AGENT_URL ?? 'http://127.0.0.1:8080';
const port = Number(process.env.FEX_API_PORT ?? 3000);
createLocalServer({ agent: new HttpAgentClient(agentUrl) }).listen(port, '127.0.0.1', () => {
  console.log(`local chat API on http://127.0.0.1:${port} -> agent ${agentUrl}`);
});
