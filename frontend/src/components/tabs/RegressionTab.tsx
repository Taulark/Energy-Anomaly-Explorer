interface RegressionTabProps {
  results: any;
}

export default function RegressionTab({ results }: RegressionTabProps) {
  if (!results || !results.regression) return (
    <div className="text-center py-12 text-gray-400">
      Run Anomaly Detection first to see regression results.
    </div>
  );

  const { regression } = results;

  return (
    <div className="space-y-6">
      {/* Model Summary */}
      <div>
        <h2 className="text-xl font-semibold text-white mb-4">Model Summary</h2>
        <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
          <div className="grid grid-cols-3 gap-4">
            <div>
              <div className="text-xs text-gray-400 mb-1">Selected Features</div>
              <div className="text-lg font-semibold text-white">
                {regression.selected_features?.length || 0}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Method</div>
              <div className="text-lg font-semibold text-white">
                {regression.method_used || 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">R² Score</div>
              <div className={`text-lg font-semibold ${
                regression.metrics?.r2 != null && regression.metrics.r2 >= 0.6 ? 'text-green-400' :
                regression.metrics?.r2 != null && regression.metrics.r2 >= 0.3 ? 'text-yellow-400' : 'text-gray-400'
              }`}>
                {regression.metrics?.r2 != null ? regression.metrics.r2.toFixed(3) : 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">RMSE</div>
              <div className="text-lg font-semibold text-white">
                {regression.metrics?.rmse != null ? regression.metrics.rmse.toFixed(2) : 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">MAE</div>
              <div className="text-lg font-semibold text-white">
                {regression.metrics?.mae != null ? regression.metrics.mae.toFixed(2) : 'N/A'}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 mb-1">Confidence</div>
              <div className={`text-lg font-semibold ${
                regression.confidence?.level === 'Strong' ? 'text-green-400' :
                regression.confidence?.level === 'Moderate' ? 'text-yellow-400' : 'text-red-400'
              }`}>
                {regression.confidence?.level || 'N/A'}
              </div>
            </div>
          </div>
          {/* Regression Warning */}
          {regression.regression_warning && (
            <div className="mt-4 pt-4 border-t border-[#2d2d44]">
              <div className="text-xs text-yellow-400">
                ⚠️ {regression.regression_warning}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Coefficients */}
      {regression.coef_table && regression.coef_table.length > 0 && (
        <div>
          <h2 className="text-xl font-semibold text-white mb-4">Coefficients</h2>
          <div className="bg-[#1e1e2e] border border-[#2d2d44] rounded-lg p-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[#2d2d44]">
                  <th className="text-left py-2 text-gray-400">Feature</th>
                  <th className="text-right py-2 text-gray-400">Coefficient</th>
                  <th className="text-right py-2 text-gray-400">Std. Coefficient</th>
                </tr>
              </thead>
              <tbody>
                {regression.coef_table.map((row: any, idx: number) => (
                  <tr key={idx} className="border-b border-[#2d2d44]">
                    <td className="py-2 text-gray-300">{row.feature}</td>
                    <td className={`text-right py-2 ${
                      (row.coefficient || 0) >= 0 ? 'text-green-400' : 'text-red-400'
                    }`}>
                      {(row.coefficient || 0).toFixed(4)}
                    </td>
                    <td className={`text-right py-2 ${
                      (row.standardized_coefficient || 0) >= 0 ? 'text-blue-400' : 'text-orange-400'
                    }`}>
                      {(row.standardized_coefficient || 0).toFixed(4)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <div className="mt-3 text-xs text-gray-500">
              <span className="font-medium">Coefficient</span>: change in load per unit change in feature.{' '}
              <span className="font-medium">Std. Coefficient</span>: change in load per one standard deviation change (comparable across features).
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
