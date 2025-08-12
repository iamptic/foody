
const express = require('express');
const path = require('path');
const app = express();
const port = process.env.PORT || 8080;
app.use(express.static(__dirname));
app.get('/', (req, res) => res.send(`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Foody</title><meta http-equiv="refresh" content="0;url=/web/buyer/">`));
app.listen(port, () => console.log('Foody web listening on', port));
