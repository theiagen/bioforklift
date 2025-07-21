

export const index = 3;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/pages/debug/_page.svelte.js')).default;
export const imports = ["_app/immutable/nodes/3.458f1cf2.js","_app/immutable/chunks/scheduler.373b8e04.js","_app/immutable/chunks/api.a517d1be.js","_app/immutable/chunks/auth.d93981a9.js","_app/immutable/chunks/index.bca36699.js"];
export const stylesheets = [];
export const fonts = [];
