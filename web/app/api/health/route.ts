/**
 * Liveness probe for the ECS Express Mode target group.
 *
 * **Deliberately does not call the API.** The obvious alternative -- health-check
 * `/`, which renders the catalogue -- couples this service's health to the
 * backend's: a brief API problem would fail the check, ECS would recycle the web
 * tasks, and a short backend blip becomes a longer whole-site outage. The API
 * has its own /health and its own alarms.
 *
 * A liveness probe answers "is this server up", not "is everything downstream
 * healthy". Those are different questions with different correct responses.
 *
 * force-dynamic so it is never prerendered into a static asset -- a cached 200
 * would keep reporting healthy after the server stopped being so.
 */
export const dynamic = "force-dynamic";

export function GET() {
  return Response.json({ status: "ok" });
}
