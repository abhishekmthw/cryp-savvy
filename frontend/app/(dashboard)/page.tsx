import { StatCards } from "@/components/dashboard/stat-cards";
import { PositionsTable } from "@/components/dashboard/positions-table";
import { PnlChart } from "@/components/dashboard/pnl-chart";
import { TradesFeed } from "@/components/dashboard/trades-feed";
import { SignalsTable } from "@/components/dashboard/signals-table";
import { LiveEvents } from "@/components/dashboard/live-events";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Dashboard</h1>

      {/* Row 1: Stat cards */}
      <StatCards />

      {/* Row 2: Positions + Chart */}
      <div className="grid grid-cols-1 xl:grid-cols-5 gap-6">
        <div className="xl:col-span-3">
          <PositionsTable />
        </div>
        <div className="xl:col-span-2">
          <PnlChart />
        </div>
      </div>

      {/* Row 3: Recent trades + Live event feed */}
      <div className="grid grid-cols-1 xl:grid-cols-2 gap-6">
        <TradesFeed />
        <LiveEvents />
      </div>
    </div>
  );
}
