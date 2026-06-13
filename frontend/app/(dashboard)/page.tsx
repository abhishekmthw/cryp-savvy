import { BotControls } from "@/components/dashboard/bot-controls";
import { StatCards } from "@/components/dashboard/stat-cards";
import { PositionsTable } from "@/components/dashboard/positions-table";
import { PnlChart } from "@/components/dashboard/pnl-chart";
import { TradesFeed } from "@/components/dashboard/trades-feed";
import { SignalsTable } from "@/components/dashboard/signals-table";
import { LiveEvents } from "@/components/dashboard/live-events";

export default function DashboardPage() {
  return (
    <div className="space-y-6">
      <BotControls />

      <StatCards />

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-5">
        <div className="xl:col-span-3">
          <PositionsTable />
        </div>
        <div className="xl:col-span-2">
          <PnlChart />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-4 xl:grid-cols-3">
        <TradesFeed />
        <SignalsTable />
        <LiveEvents />
      </div>
    </div>
  );
}
