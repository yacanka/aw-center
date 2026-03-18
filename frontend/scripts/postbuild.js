const fs = require("fs")
const path = require("path")

const dist = path.join(__dirname, "../dist")

const templates = path.join(__dirname, "../../backend/templates")
const statics = path.join(__dirname, "../../backend/core")

fs.cpSync(path.join(dist, "index.html"), path.join(templates, "index.html"))
fs.cpSync(path.join(dist, "assets"), path.join(statics, "assets"), {recursive: true})