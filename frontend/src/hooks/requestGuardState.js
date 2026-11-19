function isAnalysisKey(key) {
  return (
    key === 'compare' ||
    key === 'ast' ||
    key === 'docs' ||
    key === 'drift' ||
    (typeof key === 'string' && key.startsWith('ai:'))
  );
}

export function createRequestGuardState() {
  let generation = 0;
  let analysisGeneration = 0;
  const controllers = new Map();

  const start = (key) => {
    controllers.get(key)?.abort();
    const controller = new AbortController();
    controllers.set(key, controller);
    const requestGeneration = generation;
    const requestAnalysisGeneration = analysisGeneration;
    const analysisKey = isAnalysisKey(key);

    return {
      signal: controller.signal,
      isCurrent: () =>
        !controller.signal.aborted &&
        requestGeneration === generation &&
        (!analysisKey || requestAnalysisGeneration === analysisGeneration) &&
        controllers.get(key) === controller,
      finish: () => {
        if (controllers.get(key) === controller) {
          controllers.delete(key);
        }
      },
    };
  };

  const cancelAnalysis = () => {
    analysisGeneration += 1;
    for (const [key, controller] of controllers.entries()) {
      if (isAnalysisKey(key)) {
        controller.abort();
        controllers.delete(key);
      }
    }
  };

  const cancelAll = () => {
    generation += 1;
    analysisGeneration += 1;
    controllers.forEach((controller) => controller.abort());
    controllers.clear();
  };

  return { start, cancelAnalysis, cancelAll };
}
