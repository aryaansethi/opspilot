"use client"

import { zodResolver } from "@hookform/resolvers/zod"
import { Loader2 } from "lucide-react"
import Link from "next/link"
import { useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Label } from "@/components/ui/label"
import { errorMessage } from "@/lib/api/client"
import { useAuth } from "@/lib/auth/auth-provider"
import { AuthShell } from "../auth-shell"

const schema = z
  .object({
    display_name: z.string().trim().min(2, "At least 2 characters").max(80),
    email: z.email("Enter a valid email"),
    password: z.string().min(12, "Use at least 12 characters"),
    confirm: z.string(),
  })
  .refine((v) => v.password === v.confirm, { path: ["confirm"], message: "Passwords don't match" })
type Values = z.infer<typeof schema>

export default function RegisterPage() {
  const { register: signUp } = useAuth()
  const [formError, setFormError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { display_name: "", email: "", password: "", confirm: "" },
  })

  const onSubmit = handleSubmit(async (v) => {
    setFormError(null)
    try {
      await signUp(v.email, v.password, v.display_name)
    } catch (e) {
      setFormError(errorMessage(e))
    }
  })

  const field = (id: keyof Values, label: string, type = "text", autoComplete?: string) => (
    <div className="grid gap-1.5">
      <Label htmlFor={id}>{label}</Label>
      <Input id={id} type={type} autoComplete={autoComplete} aria-invalid={!!formState.errors[id]} {...register(id)} />
      {formState.errors[id] && <p className="text-xs text-destructive">{formState.errors[id]?.message}</p>}
    </div>
  )

  return (
    <AuthShell
      title="Create your account"
      subtitle="You'll get a personal workspace to start with."
      footer={
        <>
          Already have an account?{" "}
          <Link href="/login" className="text-foreground underline-offset-4 hover:underline">
            Sign in
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="grid gap-4" noValidate>
        {field("display_name", "Name", "text", "name")}
        {field("email", "Email", "email", "email")}
        {field("password", "Password", "password", "new-password")}
        {field("confirm", "Confirm password", "password", "new-password")}
        {formError && (
          <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {formError}
          </p>
        )}
        <Button type="submit" size="lg" disabled={formState.isSubmitting}>
          {formState.isSubmitting && <Loader2 className="animate-spin" />}
          Create account
        </Button>
      </form>
    </AuthShell>
  )
}
