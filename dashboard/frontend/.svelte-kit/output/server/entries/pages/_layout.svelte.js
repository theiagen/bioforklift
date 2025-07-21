import { c as create_ssr_component, a as subscribe, v as validate_component } from "../../chunks/ssr.js";
import { d as derived, w as writable } from "../../chunks/index.js";
import { L as LoadingSpinner } from "../../chunks/LoadingSpinner.js";
const app = "";
const authStatus = writable({ authenticated: false });
const user = writable(null);
const authLoading = writable(true);
derived(
  authStatus,
  ($authStatus) => $authStatus.authenticated
);
derived(
  authStatus,
  ($authStatus) => $authStatus.project
);
const AuthWrapper = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let $$unsubscribe_user;
  let $$unsubscribe_authStatus;
  let $$unsubscribe_authLoading;
  $$unsubscribe_user = subscribe(user, (value) => value);
  $$unsubscribe_authStatus = subscribe(authStatus, (value) => value);
  $$unsubscribe_authLoading = subscribe(authLoading, (value) => value);
  $$unsubscribe_user();
  $$unsubscribe_authStatus();
  $$unsubscribe_authLoading();
  return `  ${` <div class="min-h-screen flex items-center justify-center bg-gray-50"><div class="text-center"><div class="mb-4" data-svelte-h="svelte-1vfd0kg"><div class="text-4xl mb-2">🧬</div> <h1 class="text-2xl font-bold text-gray-900">Bioforklift Dashboard</h1> <p class="text-gray-600 mt-2">Checking authentication...</p></div> ${validate_component(LoadingSpinner, "LoadingSpinner").$$render($$result, {}, {}, {})}</div></div>`}`;
});
const Layout = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  return `${validate_component(AuthWrapper, "AuthWrapper").$$render($$result, {}, {}, {
    default: () => {
      return `${slots.default ? slots.default({}) : ``}`;
    }
  })}`;
});
export {
  Layout as default
};
