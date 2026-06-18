import type {ReactNode} from 'react';
import clsx from 'clsx';
import Heading from '@theme/Heading';
import styles from './styles.module.css';

type FeatureItem = {
  title: string;
  Svg: React.ComponentType<React.ComponentProps<'svg'>>;
  description: ReactNode;
};

const FeatureList: FeatureItem[] = [
  {
    title: 'Identity-Aware Sessions',
    Svg: require('@site/static/img/undraw_docusaurus_mountain.svg').default,
    description: (
      <>
        Every session is bound to a Keycloak user identity. JWT claims (<code>sub</code>,
        <code>email</code>, <code>roles</code>) are extracted on every request — no
        separate user lookup needed.
      </>
    ),
  },
  {
    title: 'Zero-Trust via Dapr',
    Svg: require('@site/static/img/undraw_docusaurus_tree.svg').default,
    description: (
      <>
        Dapr&apos;s bearer middleware validates every inbound JWT against Keycloak&apos;s
        JWKS endpoint before the request reaches the service. Your business logic
        never handles raw token verification.
      </>
    ),
  },
  {
    title: 'GitOps-Delivered',
    Svg: require('@site/static/img/undraw_docusaurus_react.svg').default,
    description: (
      <>
        All infrastructure — Dapr, Keycloak, Redis, and the broker itself — is
        declared in <code>gitops/</code> and continuously delivered to Kubernetes
        by Argo CD using the app-of-apps pattern.
      </>
    ),
  },
];

function Feature({title, Svg, description}: FeatureItem) {
  return (
    <div className={clsx('col col--4')}>
      <div className="text--center">
        <Svg className={styles.featureSvg} role="img" />
      </div>
      <div className="text--center padding-horiz--md">
        <Heading as="h3">{title}</Heading>
        <p>{description}</p>
      </div>
    </div>
  );
}

export default function HomepageFeatures(): ReactNode {
  return (
    <section className={styles.features}>
      <div className="container">
        <div className="row">
          {FeatureList.map((props, idx) => (
            <Feature key={idx} {...props} />
          ))}
        </div>
      </div>
    </section>
  );
}
