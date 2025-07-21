export const manifest = (() => {
function __memo(fn) {
	let value;
	return () => value ??= (value = fn());
}

return {
	appDir: "_app",
	appPath: "_app",
	assets: new Set(["favicon.png","local-test.html"]),
	mimeTypes: {".png":"image/png",".html":"text/html"},
	_: {
		client: {"start":"_app/immutable/entry/start.2ddd4661.js","app":"_app/immutable/entry/app.95a2f996.js","imports":["_app/immutable/entry/start.2ddd4661.js","_app/immutable/chunks/scheduler.373b8e04.js","_app/immutable/chunks/singletons.904c272b.js","_app/immutable/chunks/index.5ae49458.js","_app/immutable/entry/app.95a2f996.js","_app/immutable/chunks/scheduler.373b8e04.js","_app/immutable/chunks/index.bca36699.js"],"stylesheets":[],"fonts":[]},
		nodes: [
			__memo(() => import('./nodes/0.js')),
			__memo(() => import('./nodes/1.js')),
			__memo(() => import('./nodes/2.js')),
			__memo(() => import('./nodes/3.js')),
			__memo(() => import('./nodes/4.js')),
			__memo(() => import('./nodes/5.js')),
			__memo(() => import('./nodes/6.js'))
		],
		routes: [
			{
				id: "/",
				pattern: /^\/$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 2 },
				endpoint: null
			},
			{
				id: "/debug",
				pattern: /^\/debug\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 3 },
				endpoint: null
			},
			{
				id: "/simple",
				pattern: /^\/simple\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 4 },
				endpoint: null
			},
			{
				id: "/step-debug",
				pattern: /^\/step-debug\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 5 },
				endpoint: null
			},
			{
				id: "/test",
				pattern: /^\/test\/?$/,
				params: [],
				page: { layouts: [0,], errors: [1,], leaf: 6 },
				endpoint: null
			}
		],
		matchers: async () => {
			
			return {  };
		}
	}
}
})();
