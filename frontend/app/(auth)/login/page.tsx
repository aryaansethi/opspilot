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
import { IS_MOCK } from "@/lib/api/config"
import { useAuth } from "@/lib/auth/auth-provider"
import { AuthShell } from "../auth-shell"

const schema = z.object({
  email: z.email("Enter a valid email"),
  password: z.string().min(8, "At least 8 characters"),
})
type Values = z.infer<typeof schema>

export default function LoginPage() {
  const { login } = useAuth()
  const [formError, setFormError] = useState<string | null>(null)
  const { register, handleSubmit, formState } = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: IS_MOCK ? { email: "demo@opspilot.dev", password: "demo-password" } : { email: "", password: "" },
  })

  const onSubmit = handleSubmit(async (v) => {
    setFormError(null)
    try {
      await login(v.email, v.password)
    } catch (e) {
      setFormError(errorMessage(e))
    }
  })

  return (
    <AuthShell
      title="Sign in"
      subtitle="Welcome back to OpsPilot."
      footer={
        <>
          No account?{" "}
          <Link href="/register" className="text-foreground underline-offset-4 hover:underline">
            Create one
          </Link>
        </>
      }
    >
      <form onSubmit={onSubmit} className="grid gap-4" noValidate>
        <div className="grid gap-1.5">
          <Label htmlFor="email">Email</Label>
          <Input id="email" type="email" autoComplete="email" aria-invalid={!!formState.errors.email} {...register("email")} />
          {formState.errors.email && <p className="text-xs text-destructive">{formState.errors.email.message}</p>}
        </div>
        <div className="grid gap-1.5">
          <Label htmlFor="password">Password</Label>
          <Input id="password" type="password" autoComplete="current-password" aria-invalid={!!formState.errors.password} {...register("password")} />
          {formState.errors.password && <p className="text-xs text-destructive">{formState.errors.password.message}</p>}
        </div>
        {formError && (
          <p role="alert" className="rounded-md border border-destructive/30 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            {formError}
          </p>
        )}
        <Button type="submit" size="lg" disabled={formState.isSubmitting}>
          {formState.isSubmitting && <Loader2 className="animate-spin" />}
          Sign in
        </Button>
      </form>
    </AuthShell>
  )
}
