import { c as create_ssr_component, e as escape, d as add_attribute, f as each, h as createEventDispatcher, v as validate_component } from "../../chunks/ssr.js";
import { a as api } from "../../chunks/api.js";
import "chart.js/auto";
import { L as LoadingSpinner } from "../../chunks/LoadingSpinner.js";
const SystemHealthCard = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let successRate;
  let healthStatus;
  let statusColor;
  let { systemHealth } = $$props;
  if ($$props.systemHealth === void 0 && $$bindings.systemHealth && systemHealth !== void 0)
    $$bindings.systemHealth(systemHealth);
  successRate = systemHealth?.success_rate_24h || 0;
  healthStatus = successRate >= 90 ? "healthy" : successRate >= 70 ? "warning" : "critical";
  statusColor = healthStatus === "healthy" ? "green" : healthStatus === "warning" ? "yellow" : "red";
  return `<div class="card"><div class="card-header"><h2 class="card-title" data-svelte-h="svelte-1p6pufi">System Health Overview</h2> <div class="flex items-center space-x-2"><div class="${"h-3 w-3 bg-" + escape(statusColor, true) + "-500 rounded-full"}"></div> <span class="${"text-sm font-medium text-" + escape(statusColor, true) + "-700 capitalize"}">${escape(healthStatus)}</span></div></div> <div class="grid grid-cols-2 md:grid-cols-5 gap-4"><div class="text-center"><div class="metric-value">${escape((systemHealth?.samples_last_24h || 0).toLocaleString())}</div> <div class="metric-label" data-svelte-h="svelte-bgz4dc">Samples (24h)</div></div> <div class="text-center"><div class="metric-value text-green-600">${escape((systemHealth?.successful_last_24h || 0).toLocaleString())}</div> <div class="metric-label" data-svelte-h="svelte-1k41v4i">Successful</div></div> <div class="text-center"><div class="metric-value text-red-600">${escape((systemHealth?.failed_last_24h || 0).toLocaleString())}</div> <div class="metric-label" data-svelte-h="svelte-og57st">Failed</div></div> <div class="text-center"><div class="metric-value text-blue-600">${escape((systemHealth?.currently_in_progress || 0).toLocaleString())}</div> <div class="metric-label" data-svelte-h="svelte-19em9y0">In Progress</div></div> <div class="text-center"><div class="${"metric-value text-" + escape(statusColor, true) + "-600"}">${escape(successRate.toFixed(1))}%</div> <div class="metric-label" data-svelte-h="svelte-qasq4j">Success Rate</div></div></div>  <div class="mt-6 space-y-3"><div><div class="flex justify-between text-sm text-gray-600 mb-1"><span data-svelte-h="svelte-znkm4w">Success Rate (24h)</span> <span>${escape(successRate.toFixed(1))}%</span></div> <div class="w-full bg-gray-200 rounded-full h-2"><div class="${"bg-" + escape(statusColor, true) + "-600 h-2 rounded-full transition-all duration-300"}" style="${"width: " + escape(successRate, true) + "%"}"></div></div></div> ${systemHealth?.failure_rate_24h && systemHealth.failure_rate_24h > 0 ? (() => {
    let failureRate = systemHealth.failure_rate_24h;
    return ` <div><div class="flex justify-between text-sm text-gray-600 mb-1"><span data-svelte-h="svelte-52tixf">Failure Rate (24h)</span> <span>${escape(failureRate.toFixed(1))}%</span></div> <div class="w-full bg-gray-200 rounded-full h-2"><div class="bg-red-600 h-2 rounded-full transition-all duration-300" style="${"width: " + escape(failureRate, true) + "%"}"></div></div></div>`;
  })() : ``}</div></div>`;
});
const DailyRunsChart = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let { dailyRuns } = $$props;
  let chartCanvas;
  if ($$props.dailyRuns === void 0 && $$bindings.dailyRuns && dailyRuns !== void 0)
    $$bindings.dailyRuns(dailyRuns);
  return `<div class="card"><div class="card-header"><h3 class="card-title" data-svelte-h="svelte-6xkvcs">Daily Runs Trend</h3> <div class="text-sm text-gray-600">${escape(dailyRuns.length)} days of data</div></div> <div class="chart-container"><canvas${add_attribute("this", chartCanvas, 0)}></canvas></div>  ${dailyRuns.length > 0 ? (() => {
    let totalRuns = dailyRuns.reduce((sum, run) => sum + (run?.total_runs || 0), 0), avgSuccessRate = dailyRuns.reduce((sum, run) => sum + (run?.success_rate || 0), 0) / dailyRuns.length;
    return `  <div class="mt-4 grid grid-cols-2 gap-4 text-center"><div><div class="text-xl font-semibold text-primary-600">${escape(totalRuns.toLocaleString())}</div> <div class="text-sm text-gray-600" data-svelte-h="svelte-1fvo1th">Total Runs</div></div> <div><div class="text-xl font-semibold text-green-600">${escape(avgSuccessRate.toFixed(1))}%</div> <div class="text-sm text-gray-600" data-svelte-h="svelte-1rjftvs">Avg Success Rate</div></div></div>`;
  })() : ``}</div>`;
});
const WorkflowDistribution = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let { workflowDistribution } = $$props;
  let chartCanvas;
  const stateColors = {
    "Succeeded": "#22c55e",
    "Failed": "#ef4444",
    "Aborted": "#f59e0b",
    "Running": "#3b82f6",
    "Queued": "#8b5cf6",
    "Unknown": "#6b7280"
  };
  if ($$props.workflowDistribution === void 0 && $$bindings.workflowDistribution && workflowDistribution !== void 0)
    $$bindings.workflowDistribution(workflowDistribution);
  return `<div class="card"><div class="card-header"><h3 class="card-title" data-svelte-h="svelte-1i0v27e">Workflow State Distribution</h3> <div class="text-sm text-gray-600">${escape((workflowDistribution?.total_workflows || 0).toLocaleString())} total workflows</div></div> <div class="chart-container"><canvas${add_attribute("this", chartCanvas, 0)}></canvas></div>  <div class="mt-4 flex flex-wrap gap-2">${each(Object.entries(workflowDistribution?.workflow_states || {}), ([state, count]) => {
    let percentage = (workflowDistribution?.total_workflows || 0) > 0 ? (count / (workflowDistribution?.total_workflows || 1) * 100).toFixed(1) : "0.0";
    return ` <div class="flex items-center space-x-2 px-3 py-1 rounded-full text-sm" style="${"background-color: " + escape(stateColors[state] || stateColors["Unknown"], true) + "20; color: " + escape(stateColors[state] || stateColors["Unknown"], true)}"><div class="w-2 h-2 rounded-full" style="${"background-color: " + escape(stateColors[state] || stateColors["Unknown"], true)}"></div> <span class="font-medium">${escape(state)}</span> <span>${escape(count)} (${escape(percentage)}%)</span> </div>`;
  })}</div></div>`;
});
function getSuccessRateColor(rate) {
  if (rate >= 90)
    return "text-green-600";
  if (rate >= 70)
    return "text-yellow-600";
  return "text-red-600";
}
function formatProcessingTime$1(minutes) {
  if (minutes === null)
    return "N/A";
  if (minutes < 60)
    return `${minutes.toFixed(1)}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes.toFixed(0)}m`;
}
const ConfigurationTable = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let sortedConfigurations;
  let { configurations } = $$props;
  let sortColumn = "total_samples";
  if ($$props.configurations === void 0 && $$bindings.configurations && configurations !== void 0)
    $$bindings.configurations(configurations);
  sortedConfigurations = [...configurations].sort((a, b) => {
    const aValue = a[sortColumn];
    const bValue = b[sortColumn];
    if (aValue === null && bValue === null)
      return 0;
    if (aValue === null)
      return 1;
    if (bValue === null)
      return -1;
    const comparison = aValue < bValue ? -1 : aValue > bValue ? 1 : 0;
    return -comparison;
  });
  return `<div class="card"><div class="card-header"><h3 class="card-title" data-svelte-h="svelte-1tui0u8">Configuration Performance</h3> <div class="text-sm text-gray-600">${escape(configurations.length)} configurations</div></div> <div class="overflow-x-auto"><table class="min-w-full divide-y divide-gray-200"><thead class="bg-gray-50"><tr><th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"><div class="flex items-center space-x-1"><span data-svelte-h="svelte-1gr0z8s">Configuration</span> ${``}</div></th> <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"><div class="flex items-center space-x-1"><span data-svelte-h="svelte-10by0cx">Total Samples</span> ${`<svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">${`<path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M16 15l-4 4-4-4m0-6l4-4 4 4"></path>`}</svg>`}</div></th> <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"><div class="flex items-center space-x-1"><span data-svelte-h="svelte-1feqmd">Success Rate</span> ${``}</div></th> <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider" data-svelte-h="svelte-41wern">Success/Failed</th> <th class="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider cursor-pointer hover:bg-gray-100"><div class="flex items-center space-x-1"><span data-svelte-h="svelte-1rh77fa">Avg Processing Time</span> ${``}</div></th></tr></thead> <tbody class="bg-white divide-y divide-gray-200">${each(sortedConfigurations, (config) => {
    return `<tr class="hover:bg-gray-50"><td class="px-6 py-4 whitespace-nowrap"><div><div class="text-sm font-medium text-gray-900">${escape(config.config_name || "Unknown")}</div> <div class="text-sm text-gray-500">${escape(config.config_id)}</div> </div></td> <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${escape(config.total_samples.toLocaleString())}</td> <td class="px-6 py-4 whitespace-nowrap"><div class="flex items-center"><span class="${"text-sm font-medium " + escape(getSuccessRateColor(config.success_rate), true)}">${escape(config.success_rate.toFixed(1))}%</span> <div class="ml-2 w-16 bg-gray-200 rounded-full h-2"><div class="${"h-2 rounded-full " + escape(
      config.success_rate >= 90 ? "bg-green-600" : config.success_rate >= 70 ? "bg-yellow-600" : "bg-red-600",
      true
    )}" style="${"width: " + escape(config.success_rate, true) + "%"}"></div></div> </div></td> <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900"><span class="text-green-600">${escape(config.successful_samples)}</span>
              /
              <span class="text-red-600">${escape(config.failed_samples)}</span></td> <td class="px-6 py-4 whitespace-nowrap text-sm text-gray-900">${escape(formatProcessingTime$1(config.avg_processing_time_minutes))}</td> </tr>`;
  })}</tbody></table></div> ${configurations.length === 0 ? `<div class="text-center py-8 text-gray-500" data-svelte-h="svelte-epjpkp">No configuration data available</div>` : ``}</div>`;
});
function formatDate(dateString) {
  const date = new Date(dateString);
  return date.toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit"
  });
}
function getTimeDifference(created, submitted) {
  if (!submitted)
    return "N/A";
  const createdDate = new Date(created);
  const submittedDate = new Date(submitted);
  const diffMs = submittedDate.getTime() - createdDate.getTime();
  const diffMinutes = Math.floor(diffMs / (1e3 * 60));
  if (diffMinutes < 60)
    return `${diffMinutes}m`;
  const hours = Math.floor(diffMinutes / 60);
  const minutes = diffMinutes % 60;
  return `${hours}h ${minutes}m`;
}
const RecentFailures = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let displayedFailures;
  let { failures } = $$props;
  let showAll = false;
  if ($$props.failures === void 0 && $$bindings.failures && failures !== void 0)
    $$bindings.failures(failures);
  displayedFailures = failures.slice(0, 10);
  return `<div class="card"><div class="card-header"><h3 class="card-title" data-svelte-h="svelte-bhceny">Recent Failures</h3> <div class="flex items-center space-x-2"><span class="text-sm text-gray-600">${escape(failures.length)} total failures</span> ${failures.length > 10 ? `<button class="text-sm text-primary-600 hover:text-primary-700">${escape("Show All")}</button>` : ``}</div></div> ${failures.length === 0 ? `<div class="text-center py-8" data-svelte-h="svelte-iko3av"><svg class="mx-auto h-12 w-12 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z"></path></svg> <h3 class="mt-2 text-sm font-medium text-gray-900">No Recent Failures</h3> <p class="mt-1 text-sm text-gray-500">Great job! No failed workflows in recent data.</p></div>` : `<div class="space-y-3">${each(displayedFailures, (failure) => {
    return `<div class="border border-red-200 rounded-lg p-4 bg-red-50"><div class="flex justify-between items-start"><div class="flex-1"><div class="flex items-center space-x-2"><h4 class="text-sm font-medium text-gray-900">${escape(failure.entity_identifier)}</h4> <span class="status-badge status-error">${escape(failure.workflow_state)} </span></div> <div class="mt-1 text-sm text-gray-600"><span class="font-medium" data-svelte-h="svelte-1j0c6rq">Config:</span> ${escape(failure.config_name || failure.config_id || "Unknown")}</div> <div class="mt-2 grid grid-cols-2 gap-4 text-xs text-gray-500"><div><span class="font-medium" data-svelte-h="svelte-199gzt0">Created:</span> ${escape(formatDate(failure.created_at))}</div> <div><span class="font-medium" data-svelte-h="svelte-1m8vujo">Processing Time:</span> ${escape(getTimeDifference(failure.created_at, failure.submitted_at))} </div></div> ${failure.terra_submission_id ? `<div class="mt-2 text-xs text-gray-500"><span class="font-medium" data-svelte-h="svelte-1x7uvc3">Submission ID:</span> <code class="bg-gray-100 px-1 rounded">${escape(failure.terra_submission_id)}</code> </div>` : ``} ${failure.terra_workflow_id ? `<div class="mt-1 text-xs text-gray-500"><span class="font-medium" data-svelte-h="svelte-fliqg2">Workflow ID:</span> <code class="bg-gray-100 px-1 rounded">${escape(failure.terra_workflow_id)}</code> </div>` : ``}</div> <div class="flex-shrink-0 ml-4" data-svelte-h="svelte-162wjlo"><svg class="h-5 w-5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.728-.833-2.498 0L4.316 15.5c-.77.833.192 2.5 1.732 2.5z"></path></svg> </div></div> </div>`;
  })}</div> ${failures.length > 10 && !showAll ? `<div class="text-center mt-4"><button class="text-sm text-primary-600 hover:text-primary-700">Show ${escape(failures.length - 10)} more failures</button></div>` : ``}`}</div>`;
});
function formatProcessingTime(minutes) {
  if (minutes === null)
    return "N/A";
  if (minutes < 60)
    return `${minutes.toFixed(1)}m`;
  const hours = Math.floor(minutes / 60);
  const remainingMinutes = minutes % 60;
  return `${hours}h ${remainingMinutes.toFixed(0)}m`;
}
const ProcessingTimeTrends = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let validTrends;
  let avgProcessingTime;
  let totalSamples;
  let { processingTrends } = $$props;
  let chartCanvas;
  if ($$props.processingTrends === void 0 && $$bindings.processingTrends && processingTrends !== void 0)
    $$bindings.processingTrends(processingTrends);
  validTrends = processingTrends.filter((trend) => trend.avg_processing_time_minutes !== null);
  avgProcessingTime = validTrends.length > 0 ? validTrends.reduce((sum, trend) => sum + (trend.avg_processing_time_minutes || 0), 0) / validTrends.length : null;
  totalSamples = processingTrends.reduce((sum, trend) => sum + trend.sample_count, 0);
  return `<div class="card"><div class="card-header"><h3 class="card-title" data-svelte-h="svelte-xo7kre">Processing Time Trends</h3> <div class="text-sm text-gray-600">${escape(processingTrends.length)} days of data</div></div> ${validTrends.length === 0 ? `<div class="text-center py-8 text-gray-500" data-svelte-h="svelte-1utdlmk"><svg class="mx-auto h-12 w-12 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z"></path></svg> <p class="mt-2">No processing time data available</p></div>` : `<div class="chart-container"><canvas${add_attribute("this", chartCanvas, 0)}></canvas></div>  <div class="mt-4 grid grid-cols-2 gap-4 text-center"><div><div class="text-xl font-semibold text-purple-600">${escape(formatProcessingTime(avgProcessingTime))}</div> <div class="text-sm text-gray-600" data-svelte-h="svelte-1ediaqf">Avg Processing Time</div></div> <div><div class="text-xl font-semibold text-green-600">${escape(totalSamples.toLocaleString())}</div> <div class="text-sm text-gray-600" data-svelte-h="svelte-151bw26">Total Samples Processed</div></div></div>`}</div>`;
});
const ErrorCard = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let { error } = $$props;
  createEventDispatcher();
  if ($$props.error === void 0 && $$bindings.error && error !== void 0)
    $$bindings.error(error);
  return `<div class="card bg-red-50 border-red-200"><div class="flex items-center space-x-3"><div class="flex-shrink-0" data-svelte-h="svelte-jn06d0"><svg class="h-8 w-8 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.728-.833-2.498 0L4.316 15.5c-.77.833.192 2.5 1.732 2.5z"></path></svg></div> <div class="flex-1"><h3 class="text-lg font-medium text-red-800" data-svelte-h="svelte-ckycqv">Error Loading Data</h3> <p class="text-red-700 mt-1">${escape(error)}</p></div> <div class="flex-shrink-0"><button class="bg-red-600 text-white px-4 py-2 rounded-md hover:bg-red-700 transition-colors" data-svelte-h="svelte-1x8wd5u">Try Again</button></div></div></div>`;
});
const Page = create_ssr_component(($$result, $$props, $$bindings, slots) => {
  let dashboardData = null;
  let loading = true;
  let error = null;
  let lastRefresh = /* @__PURE__ */ new Date();
  let daysBack = 30;
  async function loadDashboardData() {
    try {
      loading = true;
      error = null;
      dashboardData = await api.getDashboardMetrics(daysBack);
      lastRefresh = /* @__PURE__ */ new Date();
      console.log("✅ Dashboard data loaded successfully:", dashboardData);
      console.log("📊 Daily runs:", dashboardData?.daily_runs?.length);
      console.log("💚 System health:", dashboardData?.system_health);
    } catch (err) {
      console.error("Error loading dashboard data:", err);
      error = "Failed to load dashboard data. Please check your connection and try again.";
    } finally {
      loading = false;
    }
  }
  let previousDaysBack = daysBack;
  {
    {
      if (typeof window !== "undefined" && daysBack !== previousDaysBack) {
        previousDaysBack = daysBack;
        loadDashboardData();
      }
    }
  }
  return `<div class="space-y-6"> <div class="flex justify-between items-center"><div><h2 class="text-2xl font-bold text-gray-900" data-svelte-h="svelte-fmbdhw">Dashboard Overview</h2> <p class="text-gray-600 mt-1">Last updated: ${escape(lastRefresh.toLocaleString())}</p></div> <div class="flex items-center space-x-4"><div class="flex items-center space-x-2"><label for="days-back" class="text-sm font-medium text-gray-700" data-svelte-h="svelte-rswqgg">Days back:</label> <select id="days-back" class="border border-gray-300 rounded-md px-3 py-1 text-sm focus:outline-none focus:ring-2 focus:ring-primary-500"><option${add_attribute("value", 7, 0)} data-svelte-h="svelte-bhf3hn">7 days</option><option${add_attribute("value", 30, 0)} data-svelte-h="svelte-1wq314b">30 days</option><option${add_attribute("value", 90, 0)} data-svelte-h="svelte-5tyinf">90 days</option></select></div> <button ${loading ? "disabled" : ""} class="bg-primary-600 text-white px-4 py-2 rounded-md hover:bg-primary-700 disabled:opacity-50 disabled:cursor-not-allowed flex items-center space-x-2"><svg class="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15"></path></svg> <span data-svelte-h="svelte-27y9ff">Refresh</span></button></div></div> ${loading ? `<div class="flex justify-center items-center h-64">${validate_component(LoadingSpinner, "LoadingSpinner").$$render($$result, {}, {}, {})}</div>` : `${error ? `${validate_component(ErrorCard, "ErrorCard").$$render($$result, { error }, {}, {})}` : `${dashboardData ? ` ${validate_component(SystemHealthCard, "SystemHealthCard").$$render(
    $$result,
    {
      systemHealth: dashboardData.system_health
    },
    {},
    {}
  )}  <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">${validate_component(DailyRunsChart, "DailyRunsChart").$$render($$result, { dailyRuns: dashboardData.daily_runs }, {}, {})} ${validate_component(WorkflowDistribution, "WorkflowDistribution").$$render(
    $$result,
    {
      workflowDistribution: dashboardData.workflow_distribution
    },
    {},
    {}
  )}</div>  ${validate_component(ProcessingTimeTrends, "ProcessingTimeTrends").$$render(
    $$result,
    {
      processingTrends: dashboardData.processing_trends
    },
    {},
    {}
  )}  ${validate_component(ConfigurationTable, "ConfigurationTable").$$render(
    $$result,
    {
      configurations: dashboardData.configuration_metrics
    },
    {},
    {}
  )}  ${validate_component(RecentFailures, "RecentFailures").$$render($$result, { failures: dashboardData.recent_failures }, {}, {})}` : ``}`}`}</div>`;
});
export {
  Page as default
};
