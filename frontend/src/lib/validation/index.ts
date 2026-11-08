import { z } from "zod";

export const loginSchema = z.object({
  email: z.string().trim().min(1, "Email is required").email("Invalid email address"),
  password: z.string().min(1, "Password is required"),
});

export type LoginFormData = z.infer<typeof loginSchema>;

export const taskCreateSchema = z.object({
  title: z
    .string()
    .trim()
    .max(120, "Title cannot exceed 120 characters")
    .optional()
    .or(z.literal("")),
  description: z
    .string()
    .trim()
    .min(5, "Task description must be at least 5 characters long")
    .max(10000, "Description cannot exceed 10,000 characters"),
});

export type TaskCreateFormData = z.infer<typeof taskCreateSchema>;

export const approvalSchema = z.object({
  decision: z.enum(["approved", "rejected"]),
  reason: z.string().trim().max(500, "Reason cannot exceed 500 characters").optional(),
});

export type ApprovalFormData = z.infer<typeof approvalSchema>;

export const cancelSchema = z.object({
  reason: z.string().trim().max(500, "Reason cannot exceed 500 characters").optional(),
});

export type CancelFormData = z.infer<typeof cancelSchema>;
