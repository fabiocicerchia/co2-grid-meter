@domain:dashboard @area:docs-site @from:docs/stylesheets
Feature: Browsing the documentation site privately and on-brand
  Readers of the published co2-grid-meter documentation get a site that makes no third-party font or CDN requests and does not show a borrowed logo as the project's brand.

  Background:
    Given the documentation site is published with the project theme

  @id:dashboard.docs-site.001 @rule:docs.site.no-third-party-assets @inferred @source:docs/stylesheets/extra.css#:root
  Scenario: Documentation pages render with system fonts and fetch no web fonts, CDN or analytics assets
    Given a reader whose browser blocks every host except the documentation site
    When the reader opens a documentation page
    Then body text is shown in the device's own system sans-serif font
    And code samples are shown in the device's own system monospace font
    And no request is made to a web-font service, CDN or analytics host

  @id:dashboard.docs-site.002 @rule:docs.site.no-stand-in-logo @inferred @source:docs/stylesheets/extra.css#.md-header__button.md-logo
  Scenario: The documentation header shows no generic stand-in logo
    Given the project has no logo of its own configured
    When the reader opens any documentation page
    Then the header shows the project title without a logo icon
    And the navigation drawer title shows no logo icon
