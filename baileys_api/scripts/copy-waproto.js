const fs = require('fs');
const path = require('path');

function copyDir(src, dest) {
    fs.mkdirSync(dest, { recursive: true });
    const entries = fs.readdirSync(src, { withFileTypes: true });

    for (let entry of entries) {
        const srcPath = path.join(src, entry.name);
        const destPath = path.join(dest, entry.name);

        if (entry.isDirectory()) {
            copyDir(srcPath, destPath);
        } else {
            fs.copyFileSync(srcPath, destPath);
        }
    }
}

// Copy WAProto directory to dist
const srcWAProto = path.join(__dirname, '..', 'WAProto');
const destWAProto = path.join(__dirname, '..', 'dist', 'WAProto');

console.log('Copying WAProto directory to dist...');
copyDir(srcWAProto, destWAProto);
console.log('WAProto directory copied successfully.');