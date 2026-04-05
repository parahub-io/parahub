// Export Lucide icons as SVG
const fs = require('fs');

const icons = [
  { name: 'train-track', output: 'railway.svg' },
  { name: 'recycle', output: 'recycling.svg' },
  { name: 'roller-coaster', output: 'theme_park.svg' },
  { name: 'ice-skate', output: 'ice_rink.svg' }
];

const lucidePath = '/opt/parahub/frontend/node_modules/lucide-vue-next/dist/esm/icons/';

icons.forEach(({ name, output }) => {
  const iconFile = `${lucidePath}${name}.js`;
  
  if (fs.existsSync(iconFile)) {
    const content = fs.readFileSync(iconFile, 'utf8');
    
    // Extract SVG path from lucide icon code
    // Lucide format: ['svg', { ... }, ['path', { d: '...' }]]
    const pathMatch = content.match(/d:\s*["']([^"']+)["']/);
    
    if (pathMatch) {
      const pathData = pathMatch[1];
      
      // Create 15x15 SVG with the path (Lucide default is 24x24)
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="${pathData}" />
</svg>`;
      
      fs.writeFileSync(`/tmp/parahub_sprite/icons/${output}`, svg);
      console.log(`✅ Exported ${name} → ${output}`);
    }
  } else {
    console.log(`❌ Not found: ${name}`);
  }
});

// Add more icons
const moreIcons = [
  { name: 'snowflake', output: 'ice_rink.svg' },
  { name: 'construction', output: 'bollard.svg' }
];

moreIcons.forEach(({ name, output }) => {
  const iconFile = `${lucidePath}${name}.js`;
  
  if (fs.existsSync(iconFile)) {
    const content = fs.readFileSync(iconFile, 'utf8');
    const pathMatch = content.match(/d:\s*["']([^"']+)["']/);
    
    if (pathMatch) {
      const pathData = pathMatch[1];
      const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="${pathData}" />
</svg>`;
      
      fs.writeFileSync(`/tmp/parahub_sprite/icons/${output}`, svg);
      console.log(`✅ Exported ${name} → ${output}`);
    }
  } else {
    console.log(`❌ Not found: ${name}`);
  }
});
