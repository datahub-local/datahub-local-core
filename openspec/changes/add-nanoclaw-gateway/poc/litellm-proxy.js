// PoC credential forwarder. Agents point ANTHROPIC_BASE_URL here; this process
// adds the LiteLLM key. Keep it boring: one upstream, no caching, no retries.
const http = require('http');
const fs = require('fs');

const KEY = fs.readFileSync(process.env.KEY_FILE || '/etc/nanoclaw/litellm-key', 'utf8').trim();
const UPSTREAM = new URL(process.env.LITELLM_URL || 'http://datahub-local-core-data-litellm.data.svc.cluster.local:4000');
const PORT = Number(process.env.PORT || 4001);

const server = http.createServer((req, res) => {
  const chunks = [];
  req.on('data', (c) => chunks.push(c));
  req.on('end', () => {
    const body = Buffer.concat(chunks);
    const headers = { ...req.headers };
    delete headers.host;
    delete headers['content-length'];
    delete headers.authorization;
    delete headers['x-api-key'];
    headers['x-api-key'] = KEY;
    headers['content-length'] = String(body.length);

    const upstream = (UPSTREAM.protocol === 'https:' ? require('https') : http).request(
      {
        protocol: UPSTREAM.protocol,
        hostname: UPSTREAM.hostname,
        port: UPSTREAM.port || (UPSTREAM.protocol === 'https:' ? 443 : 80),
        path: req.url,
        method: req.method,
        headers,
      },
      (up) => {
        res.writeHead(up.statusCode || 502, up.headers);
        up.pipe(res);
      },
    );
    upstream.on('error', (error) => {
      console.error('upstream error', error.message);
      res.writeHead(502, { 'content-type': 'application/json' });
      res.end(JSON.stringify({ error: error.message }));
    });
    upstream.end(body);
  });
});

server.listen(PORT, '0.0.0.0', () => console.log(`forwarding :${PORT} -> ${UPSTREAM.origin}`));
