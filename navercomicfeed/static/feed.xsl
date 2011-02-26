<?xml version="1.0" encoding="utf-8"?>
<!-- 네이버 웹툰 RSS 스타일 -->
<xsl:stylesheet version="1.0"
                xmlns:xsl="http://www.w3.org/1999/XSL/Transform"
                xmlns:atom="http://www.w3.org/2005/Atom"
                xmlns:dc="http://purl.org/dc/elements/1.1/">
  <xsl:output method="html" encoding="utf-8"/>
	
  <xsl:template match="/">
    <html xmlns="http://www.w3.org/1999/xhtml">
      <head>
        <title>
          <xsl:apply-templates select="/atom:feed/atom:title/text()" />
        </title>
        <link rel="stylesheet"
              href="{normalize-space(substring-after(
                     /atom:feed/atom:generator, '|'))}"
              type="text/css" />
      </head>
      <body>
        <header>
          <h1>
            <a href="{/atom:feed/atom:link[contains(concat(' ', @rel, ' '),
                                                    ' alternate ')]/@href}"
               rel="alternate">
              <xsl:value-of select="/atom:feed/atom:title" />
            </a>
          </h1>
          <p><xsl:value-of select="/atom:feed/atom:subtitle" /></p>
        </header>
        <div class="articles">
          <xsl:apply-templates select="/atom:feed/atom:entry">
            <xsl:sort select="atom:published" order="descending" />
          </xsl:apply-templates>
        </div>
        <footer>
          <p>이 URL은 <a href="{atom:feed/atom:generator/@uri}">
             네이버 웹툰 RSS</a>에서 제공하는 Atom 형식의 XML 문서입니다.</p>
        </footer>
      </body>
    </html>
  </xsl:template>
  
  <xsl:template match="atom:entry">
    <article>
      <time datetime="{atom:updated}">
        <span class="date">
          <xsl:value-of select="substring-before(atom:updated, 'T')" />
        </span>
        <span class="time">
          <xsl:value-of select="substring(atom:updated, 12, 8)" />
        </span>
      </time>
      <h2>
        <a href="{atom:link/@href}"><xsl:value-of select="atom:title" /></a>
      </h2>
      <div class="images">
        <xsl:apply-templates select="atom:link[contains(concat(' ', @rel, ' '),
                                                        ' enclosure ')]" />
      </div>
      <p><xsl:value-of select="atom:summary" /></p>
    </article>
  </xsl:template>

  <xsl:template match="atom:link">
    <div><img src="{@href}" alt="" /></div>
  </xsl:template>
</xsl:stylesheet>

