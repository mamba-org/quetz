<template>
  <div id="app">
    <Header />
    <cv-content id="main-content" class="container">
      <router-view />
    </cv-content>
  </div>
</template>

<script>
import Header from './components/Header';
export default {
  name: 'App',
  components: {
    Header
  }
};
</script>

<style lang="scss">
@import './styles/carbon';

.container
{
  min-height: calc(100vh - 48px);
}

.bx--data-table thead,
.bx--data-table th
{
  background: $carbon--gray-90;
}

.quetz-main-table {
  margin-top: 2rem;
  margin-bottom: 2rem;
}
</style>
