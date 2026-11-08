import { Clock } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ExecutionEventRead, TaskStatus } from "@/types/backend";
import { formatDate } from "@/lib/formatters";
import { TASK_STATUS_CONFIG } from "@/lib/status/statusConfig";

interface ExecutionTimelineProps {
  taskStatus?: TaskStatus;
  events: ExecutionEventRead[];
}

export function ExecutionTimeline({ taskStatus, events }: ExecutionTimelineProps) {
  // Sort events chronologically
  const sortedEvents = [...events].sort(
    (a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime()
  );

  const statusMeta = taskStatus ? TASK_STATUS_CONFIG[taskStatus] : null;

  return (
    <Card className="bg-[#111820] border-white/8 shadow-sm">
      <CardHeader className="pb-3 border-b border-white/[0.06]">
        <div className="flex items-center justify-between">
          <div>
            <CardTitle className="text-base font-semibold text-white flex items-center gap-2">
              <Clock className="h-4 w-4 text-[#55D6C2]" />
              Execution Lifecycle Timeline
            </CardTitle>
            <CardDescription className="text-xs text-zinc-400">
              Audit trail of deterministic state transitions and microVM events
            </CardDescription>
          </div>
          <div className="flex items-center gap-2">
            {statusMeta && (
              <Badge variant="outline" className={`text-xs ${statusMeta.badgeClass}`}>
                <span className={`h-1.5 w-1.5 rounded-full mr-1.5 ${statusMeta.dotClass}`} />
                {statusMeta.label}
              </Badge>
            )}
            <Badge variant="outline" className="font-mono text-xs">
              {events.length} Recorded Events
            </Badge>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-4">
        {sortedEvents.length === 0 ? (
          <p className="text-xs text-zinc-400 py-3 text-center">
            No execution events recorded yet.
          </p>
        ) : (
          <div className="relative pl-6 space-y-4 before:absolute before:left-2.5 before:top-2 before:bottom-2 before:w-px before:bg-white/10">
            {sortedEvents.map((ev, idx) => {
              const isError =
                ev.event_type.includes("failed") ||
                ev.event_type.includes("error") ||
                ev.event_type.includes("leak");
              const isSuccess =
                ev.event_type.includes("succeeded") ||
                ev.event_type.includes("verified");

              return (
                <div key={ev.id || idx} className="relative group text-xs">
                  {/* Timeline node */}
                  <span
                    className={`absolute -left-6 top-1 h-3 w-3 rounded-full border-2 border-[#111820] ${
                      isError
                        ? "bg-rose-400"
                        : isSuccess
                        ? "bg-emerald-400"
                        : "bg-[#55D6C2]"
                    }`}
                  />

                  <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                    <span className="font-mono font-semibold text-zinc-200 uppercase text-[11px]">
                      {ev.event_type.replace(/_/g, " ")}
                    </span>
                    <span className="text-[10px] font-mono text-zinc-400">
                      {formatDate(ev.timestamp)}
                    </span>
                  </div>

                  <p className="text-zinc-400 text-xs mt-0.5 leading-relaxed">
                    {ev.message}
                  </p>
                </div>
              );
            })}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
