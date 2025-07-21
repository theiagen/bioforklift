

export const index = 1;
let component_cache;
export const component = async () => component_cache ??= (await import('../entries/fallbacks/error.svelte.js')).default;
export const imports = ["_app/immutable/nodes/1.6dd3ade8.js","_app/immutable/chunks/scheduler.373b8e04.js","_app/immutable/chunks/index.bca36699.js","_app/immutable/chunks/singletons.904c272b.js","_app/immutable/chunks/index.5ae49458.js"];
export const stylesheets = [];
export const fonts = [];
