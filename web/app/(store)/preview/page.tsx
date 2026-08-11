"use client";

import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Card, CardBody, CardHeader, CardTitle } from "@/components/ui/card";
import { FormField } from "@/components/ui/form-field";
import { Input } from "@/components/ui/input";
import { Modal } from "@/components/ui/modal";
import { TBody, TD, TH, THead, TR, Table } from "@/components/ui/table";
import { ToastProvider, useToast } from "@/components/ui/toast";

/**
 * Every primitive in every state, on one page.
 *
 * Exists so the set can be seen together and checked against Section 4.3's
 * quality floor -- tab through it, confirm focus is visible on each control,
 * confirm Escape closes the modal and returns focus to the trigger.
 */

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="mt-8">
      <h2 className="mb-3 font-display text-xl text-text">{title}</h2>
      {children}
    </section>
  );
}

function Preview() {
  const [modalOpen, setModalOpen] = useState(false);
  const { toast } = useToast();

  return (
    <main className="mx-auto max-w-3xl p-8">
      <h1 className="font-display text-3xl text-text">UI primitives</h1>
      <p className="mt-2 font-body text-base text-muted">
        Shared by the storefront and the Phase 4 vendor portal.
      </p>

      <Section title="Button">
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="primary">Primary</Button>
          <Button variant="accent">Accent</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="danger">Danger</Button>
          <Button disabled>Disabled</Button>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Button size="sm">Small</Button>
          <Button size="md">Medium</Button>
          <Button size="lg">Large</Button>
        </div>
      </Section>

      <Section title="Card">
        <Card>
          <CardHeader>
            <CardTitle>Classic Cotton Tee</CardTitle>
          </CardHeader>
          <CardBody>
            <p className="font-body text-base text-muted">
              Midweight combed cotton, cut boxy and pre-shrunk.
            </p>
          </CardBody>
        </Card>
      </Section>

      <Section title="Form field">
        <div className="flex flex-col gap-4">
          <FormField id="email" label="Email" hint="We never share it." required>
            {(control) => <Input type="email" placeholder="you@example.com" {...control} />}
          </FormField>
          <FormField id="sku" label="SKU" error="That SKU is already in use.">
            {(control) => <Input defaultValue="TEE-CLS-S-BLK" invalid {...control} />}
          </FormField>
        </div>
      </Section>

      <Section title="Table">
        <Table>
          <THead>
            <TR>
              <TH>SKU</TH>
              <TH>Variant</TH>
              <TH>Stock</TH>
            </TR>
          </THead>
          <TBody>
            <TR>
              <TD>TEE-CLS-S-BLK</TD>
              <TD>Small / Black</TD>
              <TD>25</TD>
            </TR>
            <TR>
              <TD>TEE-CLS-M-WHT</TD>
              <TD>Medium / White</TD>
              <TD>0</TD>
            </TR>
          </TBody>
        </Table>
      </Section>

      <Section title="Modal and toast">
        <div className="flex flex-wrap gap-2">
          <Button onClick={() => setModalOpen(true)}>Open modal</Button>
          <Button variant="ghost" onClick={() => toast("Added to cart")}>
            Toast: info
          </Button>
          <Button variant="ghost" onClick={() => toast("Product saved", "success")}>
            Toast: success
          </Button>
          <Button variant="ghost" onClick={() => toast("Card declined", "error")}>
            Toast: error
          </Button>
        </div>
      </Section>

      <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Delete product?">
        <p className="text-muted">
          This hides the product from the storefront. Past orders are unaffected.
        </p>
        <div className="mt-4 flex justify-end gap-2">
          <Button variant="ghost" onClick={() => setModalOpen(false)}>
            Cancel
          </Button>
          <Button variant="danger" onClick={() => setModalOpen(false)}>
            Delete
          </Button>
        </div>
      </Modal>
    </main>
  );
}

export default function PreviewPage() {
  return (
    <ToastProvider>
      <Preview />
    </ToastProvider>
  );
}
