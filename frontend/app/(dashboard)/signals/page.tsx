import { FullSignalsTable } from "@/components/dashboard/full-signals-table";

export default function SignalsPage() {
  return (
    <div className="space-y-6">
      <h1 className="text-xl font-semibold text-white">Signal Scanner</h1>
      <FullSignalsTable />
    </div>
  );
}
