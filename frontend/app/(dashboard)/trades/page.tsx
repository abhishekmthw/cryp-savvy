import { FullTradesTable } from "@/components/dashboard/full-trades-table";

export default function TradesPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Trade History</h1>
      <FullTradesTable />
    </div>
  );
}
