import { c as create_ssr_component, e as escape } from "./ssr.js";
const LoadingSpinner = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let { size = "md" } = $$props;
  let { color = "primary-600" } = $$props;
  const sizeClasses = {
    sm: "h-4 w-4",
    md: "h-8 w-8",
    lg: "h-12 w-12"
  };
  if ($$props.size === void 0 && $$bindings.size && size !== void 0)
    $$bindings.size(size);
  if ($$props.color === void 0 && $$bindings.color && color !== void 0)
    $$bindings.color(color);
  return `<div class="flex justify-center items-center"><div class="${"loading-spinner " + escape(sizeClasses[size], true) + " border-" + escape(color, true)}"></div></div>`;
});
export {
  LoadingSpinner as L
};
