

export const index = 6;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/test/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/6.b02bc0df.js","_app/immutable/chunks/scheduler.373b8e04.js","_app/immutable/chunks/index.bca36699.js"];
export const stylesheets = [];
export const fonts = [];
