const fs = require('fs');
let data = fs.readFileSync('src/pages/RecommendPage.jsx', 'utf8');
data = data.replace('buffer.split(\"

\")', 'buffer.split("\\n\\n")');
data = data.replace('buffer.split(\"

\")', 'buffer.split("\\n\\n")');
data = data.replace('part.trim().split(\"
\")', 'part.trim().split("\\n")');
data = data.replace('part.trim().split(\"
\")', 'part.trim().split("\\n")');
fs.writeFileSync('src/pages/RecommendPage.jsx', data);
