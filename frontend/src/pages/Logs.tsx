import React from 'react';
import { PageHeader } from '../components/layout/PageHeader';
import { LogSearch } from '../components/logs/LogSearch';

export const Logs: React.FC = () => {
  return (
    <div>
      <PageHeader
        title="Log Intelligence & Vector Search"
        description="Search production logs using dense embeddings, secret redaction, and template clustering."
      />
      <LogSearch />
    </div>
  );
};
