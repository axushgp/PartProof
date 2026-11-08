"use client";

import { useState, useMemo } from "react";
import Link from "next/link";
import { useQuery } from "@tanstack/react-query";
import {
  ArrowUpDown,
  Filter,
  Plus,
  RefreshCw,
  Search,
  FileCode2,
  ChevronRight,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { api } from "@/lib/api/client";
import { getTaskStatusMeta } from "@/lib/status/statusConfig";
import { formatDate } from "@/lib/formatters";

export default function TasksPage() {
  const [searchQuery, setSearchQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("all");
  const [sortOrder, setSortOrder] = useState<"newest" | "oldest">("newest");

  const {
    data: tasks,
    isLoading,
    isError,
    refetch,
    isFetching,
  } = useQuery({
    queryKey: ["tasks"],
    queryFn: api.tasks.list,
  });

  const filteredTasks = useMemo(() => {
    if (!tasks) return [];
    let list = [...tasks];

    // Search filter
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (t) =>
          t.title.toLowerCase().includes(q) ||
          t.description.toLowerCase().includes(q) ||
          t.id.toLowerCase().includes(q)
      );
    }

    // Status filter
    if (statusFilter !== "all") {
      if (statusFilter === "active") {
        list = list.filter((t) =>
          ["queued", "preparing", "running", "verifying", "cancel_requested"].includes(t.status)
        );
      } else if (statusFilter === "terminal") {
        list = list.filter((t) =>
          ["succeeded", "failed", "cancelled", "timed_out", "rejected"].includes(t.status)
        );
      } else {
        list = list.filter((t) => t.status === statusFilter);
      }
    }

    // Sorting
    list.sort((a, b) => {
      const timeA = new Date(a.created_at).getTime();
      const timeB = new Date(b.created_at).getTime();
      return sortOrder === "newest" ? timeB - timeA : timeA - timeB;
    });

    return list;
  }, [tasks, searchQuery, statusFilter, sortOrder]);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-2 border-b border-white/[0.06]">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white flex items-center gap-2.5">
            Tasks &amp; Audits
            {isFetching && <RefreshCw className="h-4 w-4 animate-spin text-zinc-400" />}
          </h1>
          <p className="text-xs text-zinc-400 mt-1">
            Complete inventory of submitted natural language tasks, AI execution plans, and isolated microVM runs.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <Button
            variant="outline"
            size="sm"
            onClick={() => refetch()}
            disabled={isFetching}
            className="text-xs gap-1.5 h-8"
          >
            <RefreshCw className={`h-3.5 w-3.5 ${isFetching ? "animate-spin" : ""}`} />
            <span>Refresh</span>
          </Button>

          <Button asChild variant="default" size="sm" className="text-xs gap-1.5 h-8">
            <Link href="/app/tasks/new">
              <Plus className="h-3.5 w-3.5" />
              <span>Create Task</span>
            </Link>
          </Button>
        </div>
      </div>

      {/* Filter and Search Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-3 bg-[#111820] p-3 rounded-lg border border-white/8">
        {/* Search */}
        <div className="relative flex-1">
          <Search className="absolute left-3 top-2.5 h-4 w-4 text-zinc-400 pointer-events-none" />
          <Input
            placeholder="Search by title, description or task ID..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="pl-9 h-9 text-xs"
          />
        </div>

        {/* Status Filter */}
        <div className="flex items-center gap-2">
          <Filter className="h-3.5 w-3.5 text-zinc-400 hidden sm:inline-block" />
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="h-9 rounded-md border border-white/10 bg-[#0B0E12] px-3 py-1 text-xs text-zinc-200 focus:outline-none focus:ring-1 focus:ring-[#55D6C2] focus:border-[#55D6C2]"
            aria-label="Filter by status"
          >
            <option value="all">All Statuses</option>
            <option value="awaiting_approval">Awaiting Approval</option>
            <option value="active">Active Executions</option>
            <option value="succeeded">Succeeded</option>
            <option value="failed">Failed</option>
            <option value="needs_reconciliation">Needs Reconciliation</option>
            <option value="terminal">All Terminal</option>
          </select>

          {/* Sort order */}
          <Button
            variant="outline"
            size="sm"
            onClick={() => setSortOrder(sortOrder === "newest" ? "oldest" : "newest")}
            className="h-9 px-3 text-xs gap-1.5 shrink-0"
            title={`Sort: ${sortOrder === "newest" ? "Newest First" : "Oldest First"}`}
          >
            <ArrowUpDown className="h-3.5 w-3.5 text-zinc-400" />
            <span className="hidden sm:inline-block">
              {sortOrder === "newest" ? "Newest" : "Oldest"}
            </span>
          </Button>
        </div>
      </div>

      {/* Table Container */}
      <Card className="bg-[#111820] border-white/8 shadow-sm overflow-hidden">
        <CardContent className="p-0">
          {isLoading ? (
            <div className="p-6 space-y-4">
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
              <Skeleton className="h-12 w-full" />
            </div>
          ) : isError ? (
            <div className="p-10 text-center space-y-3">
              <p className="text-sm text-rose-300">Unable to load tasks from backend.</p>
              <Button variant="outline" size="sm" onClick={() => refetch()} className="text-xs">
                Retry
              </Button>
            </div>
          ) : filteredTasks.length === 0 ? (
            <div className="p-12 text-center space-y-3">
              <FileCode2 className="mx-auto h-9 w-9 text-zinc-600 mb-1" />
              <p className="text-sm font-medium text-zinc-300">
                {searchQuery || statusFilter !== "all"
                  ? "No tasks match your filter criteria"
                  : "No engineering tasks found"}
              </p>
              <p className="text-xs text-zinc-400 max-w-sm mx-auto">
                {searchQuery || statusFilter !== "all"
                  ? "Try adjusting your search terms or clearing status filters."
                  : "Create an autonomous engineering task to generate an isolated execution plan."}
              </p>
              {searchQuery || statusFilter !== "all" ? (
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => {
                    setSearchQuery("");
                    setStatusFilter("all");
                  }}
                  className="text-xs mt-2"
                >
                  Clear Filters
                </Button>
              ) : (
                <Button asChild variant="default" size="sm" className="text-xs mt-2">
                  <Link href="/app/tasks/new">Create Task</Link>
                </Button>
              )}
            </div>
          ) : (
            <div className="overflow-x-auto" data-lenis-prevent>
              <table className="w-full text-left text-xs text-zinc-300">
                <thead className="bg-[#0B0E12] text-zinc-400 uppercase text-[10px] tracking-wider font-mono border-b border-white/[0.08]">
                  <tr>
                    <th scope="col" className="py-3 px-4">Task &amp; ID</th>
                    <th scope="col" className="py-3 px-4 hidden md:table-cell">Description</th>
                    <th scope="col" className="py-3 px-4">Status</th>
                    <th scope="col" className="py-3 px-4 hidden sm:table-cell">Created</th>
                    <th scope="col" className="py-3 px-4 text-right">Action</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-white/[0.06]">
                  {filteredTasks.map((task) => {
                    const statusMeta = getTaskStatusMeta(task.status);
                    return (
                      <tr
                        key={task.id}
                        className="hover:bg-white/[0.025] transition-colors group"
                      >
                        <td className="py-3.5 px-4 font-medium text-white max-w-xs">
                          <Link
                            href={`/app/tasks/${task.id}`}
                            className="block space-y-0.5 group-hover:text-[#55D6C2] transition-colors"
                          >
                            <span className="font-semibold block truncate">{task.title}</span>
                            <span className="font-mono text-[10px] text-zinc-400">
                              {task.id}
                            </span>
                          </Link>
                        </td>

                        <td className="py-3.5 px-4 text-zinc-400 hidden md:table-cell max-w-md">
                          <p className="line-clamp-2 leading-relaxed">{task.description}</p>
                        </td>

                        <td className="py-3.5 px-4 whitespace-nowrap">
                          <Badge
                            variant="default"
                            className={statusMeta.badgeClass}
                            dotClass={statusMeta.dotClass}
                          >
                            {statusMeta.label}
                          </Badge>
                        </td>

                        <td className="py-3.5 px-4 text-zinc-400 font-mono text-[11px] whitespace-nowrap hidden sm:table-cell">
                          {formatDate(task.created_at)}
                        </td>

                        <td className="py-3.5 px-4 text-right whitespace-nowrap">
                          <Button
                            asChild
                            variant="ghost"
                            size="sm"
                            className="h-7 px-2 text-xs text-zinc-400 hover:text-white gap-1"
                          >
                            <Link href={`/app/tasks/${task.id}`}>
                              <span>Details</span>
                              <ChevronRight className="h-3 w-3" />
                            </Link>
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
