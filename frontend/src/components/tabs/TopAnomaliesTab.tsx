interface TopAnomaliesTabProps {
  results: any;
}

export default function TopAnomaliesTab({ results }: TopAnomaliesTabProps) {
  if (!results || !results.top_anomalies) return null;

  const zThresholdUsed = results.z_threshold_used || 2.0;
  const topNUsed = results.top_n_used || 50;
  const yearFilterUsed = results.year_filter_used || "All";
  
  // Determine table title based on year filter
  const tableTitle = yearFilterUsed === "All" 
    ? `Top ${topNUsed} per Year`
    : `Top ${topNUsed} Anomalies in ${yearFilterUsed}`;

  return (
    <div className="space-y-6">
      <div className="mb-4 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <h2 className="text-lg font-semibold text-white sm:text-xl">{tableTitle}</h2>
        <span className="shrink-0 text-xs text-gray-400">Z-threshold: {zThresholdUsed.toFixed(1)}</span>
      </div>
      
      <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[#2d2d44]">
                <th className="text-left py-2 text-gray-400">DateTime</th>
                <th className="text-right py-2 text-gray-400">Actual</th>
                <th className="text-right py-2 text-gray-400">Predicted</th>
                <th className="text-right py-2 text-gray-400">Residual</th>
                <th className="text-right py-2 text-gray-400">Z-Score</th>
                <th className="text-right py-2 text-gray-400">|Z-Score|</th>
              </tr>
            </thead>
            <tbody>
              {results.top_anomalies.slice(0, 50).map((item: any, idx: number) => (
                <tr key={idx} className="border-b border-[#2d2d44] hover:bg-[#252538]">
                  <td className="py-2 text-gray-300">
                    {new Date(item.hour_datetime).toLocaleString()}
                  </td>
                  <td className="text-right py-2 text-white">{item.actual?.toFixed(2)}</td>
                  <td className="text-right py-2 text-gray-400">{item.predicted?.toFixed(2)}</td>
                  <td className="text-right py-2 text-gray-400">{item.residual?.toFixed(2)}</td>
                  <td className="text-right py-2 text-red-400">{item.z_score?.toFixed(2)}</td>
                  <td className="text-right py-2 text-yellow-400">{item.abs_z?.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
